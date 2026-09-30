import os
import re
import asyncio
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

try:
    import openai
except ImportError:
    raise ImportError("Please install openai: pip install openai")

try:
    import PyPDF2
except ImportError:
    raise ImportError("Please install PyPDF2: pip install PyPDF2")


GLOSSARY_PROMPT = (
    "Use these fixed translations for the terms below (text after # is a note, not part of the translation):\n"
    "{glossary_text}"
)


def load_glossary(path: str) -> Dict[str, str]:
    """Parse sakura (src->dst #note), galtransl (src<TAB>dst) or MIT (src dst #note) glossary files."""
    entries: Dict[str, str] = {}
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(('#', '//', '\\\\')):
                continue
            if '->' in line:
                src, dst = line.split('->', 1)
            else:
                parts = re.split(r'\t+| {2,}', line, maxsplit=1)
                if len(parts) < 2:
                    parts = line.split(None, 1)
                if len(parts) < 2:
                    continue
                src, dst = parts[0].replace('_', ' '), parts[1]
            src, dst = src.strip(), ' '.join(dst.split())
            if src and dst:
                entries[src] = dst
    return entries


class DeepSeekTranslator:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: str = "deepseek-chat",
        temperature: float = 0.3,
        top_p: float = 1.0,
        context: Optional[str] = None,
        glossary_path: Optional[str] = None,
    ):
        self.context = context
        self.glossary = load_glossary(glossary_path) if glossary_path else {}
        if glossary_path:
            print(f"Loaded {len(self.glossary)} glossary entries from {glossary_path}")

        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required")

        self.api_base = api_base or os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p

        self.client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base
        )

        self._MAX_TOKENS = 8000
        self._MAX_TOKENS_IN = self._MAX_TOKENS // 2
        self._TIMEOUT = 40
        self._RETRY_ATTEMPTS = 3

        self.token_count = 0
        self.token_count_last = 0

    def _get_system_prompt(self, to_lang: str) -> str:
        prompt = f"""You are a professional translator. Translate the given text to {to_lang}.
Requirements:
1. Preserve the original meaning and tone
2. Use natural and fluent expressions in the target language
3. Maintain formatting (line breaks, numbers, etc.)
4. Output ONLY the translation, no explanations
"""
        if self.context:
            prompt += f"""
Background on the source work (use it to keep names, terminology and tone consistent):
{self.context}
"""
        return prompt + """
Format: Each line will be prefixed with <|N|> where N is the line number.
Respond with translations in the same format."""

    def _relevant_terms(self, text: str) -> Dict[str, str]:
        # Only send terms that appear in this batch, so big glossaries don't bloat every prompt.
        found = {}
        lowered = text.lower()
        for src, dst in self.glossary.items():
            try:
                hit = re.search(src, text, re.IGNORECASE)
            except re.error:
                hit = src.lower() in lowered
            if hit:
                found[src] = dst
        return found

    def count_tokens(self, text: str) -> int:
        """Estimate token count (conservative)"""
        return len(text.encode('utf-8'))

    def _split_text_into_batches(self, lines: List[str]) -> List[List[str]]:
        """Split text lines into batches that fit within token limits"""
        batches = []
        current_batch = []
        current_length = 0

        for line in lines:
            line_tokens = self.count_tokens(line) + 20  # Buffer for <|N|> tag

            if current_batch and (current_length + line_tokens) > self._MAX_TOKENS_IN:
                batches.append(current_batch)
                current_batch = []
                current_length = 0

            current_batch.append(line)
            current_length += line_tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    def _parse_by_id(self, content: str, n: int) -> List[Optional[str]]:
        result: List[Optional[str]] = [None] * n
        matches = list(re.finditer(r'<\|(\d+)\|>(.*?)(?=<\|\d+\|>|\Z)', content, re.DOTALL))
        if not matches and n == 1 and content.strip():
            result[0] = ' '.join(content.split())
        for m in matches:
            i = int(m.group(1)) - 1
            text = ' '.join(m.group(2).split())
            if 0 <= i < n and text:
                result[i] = text
        return result

    async def _translate_batch(
        self,
        batch: List[str],
        from_lang: str,
        to_lang: str
    ) -> List[str]:
        """Translate a single batch of text lines"""
        prompt = "\n".join([f"<|{i+1}|>{line}" for i, line in enumerate(batch)])

        messages = [{"role": "system", "content": self._get_system_prompt(to_lang)}]
        terms = self._relevant_terms("\n".join(batch))
        if terms:
            glossary_text = "\n".join(f"{src}->{dst}" for src, dst in terms.items())
            messages.append({"role": "system", "content": GLOSSARY_PROMPT.format(glossary_text=glossary_text)})
        messages.append({"role": "user", "content": prompt})

        parsed: List[Optional[str]] = [None] * len(batch)
        missing = list(range(len(batch)))
        for attempt in range(self._RETRY_ATTEMPTS):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self._MAX_TOKENS,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    timeout=self._TIMEOUT
                )
            except Exception as e:
                if attempt == self._RETRY_ATTEMPTS - 1:
                    raise Exception(f"Translation failed after {self._RETRY_ATTEMPTS} attempts: {e}")
                await asyncio.sleep(1)
                continue

            if hasattr(response, 'usage') and hasattr(response.usage, 'total_tokens'):
                self.token_count += response.usage.total_tokens
                self.token_count_last = response.usage.total_tokens

            content = response.choices[0].message.content or ''
            for i, t in enumerate(self._parse_by_id(content, len(batch))):
                if t is not None:
                    parsed[i] = t
            missing = [i for i, t in enumerate(parsed) if t is None]
            if not missing:
                return parsed
            print(f"  {len(missing)}/{len(batch)} lines missing from response, retrying ({attempt + 1}/{self._RETRY_ATTEMPTS})")

        # Recurse on strictly smaller inputs so this always terminates.
        if len(batch) == 1:
            print("  Warning: line could not be translated, keeping original")
            return list(batch)
        if len(missing) < len(batch):
            retry = await self._translate_batch([batch[i] for i in missing], from_lang, to_lang)
            for i, t in zip(missing, retry):
                parsed[i] = t
            return parsed
        mid = len(batch) // 2
        return (await self._translate_batch(batch[:mid], from_lang, to_lang)
                + await self._translate_batch(batch[mid:], from_lang, to_lang))

    async def translate_text(
        self,
        text: str,
        from_lang: str = "auto",
        to_lang: str = "Chinese"
    ) -> str:
        """Translate plain text"""
        lines = text.split('\n')
        # Blank lines stay in place locally so paragraph breaks can't shift.
        idx = [i for i, line in enumerate(lines) if line.strip()]
        if not idx:
            return text

        batches = self._split_text_into_batches([lines[i] for i in idx])
        out = list(lines)
        pos = 0

        for n, batch in enumerate(batches, 1):
            print(f"Translating batch {n}/{len(batches)}...")
            for t in await self._translate_batch(batch, from_lang, to_lang):
                out[idx[pos]] = t
                pos += 1

        return '\n'.join(out)

    async def translate_file(
        self,
        input_path: str,
        output_path: str,
        from_lang: str = "auto",
        to_lang: str = "Chinese"
    ):
        """Translate a text file"""
        with open(input_path, 'r', encoding='utf-8') as f:
            text = f.read()

        translated = await self.translate_text(text, from_lang, to_lang)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(translated)

        print(f"Translation saved to: {output_path}")
        if self.token_count_last:
            print(f"Used {self.token_count_last} tokens (Total: {self.token_count})")

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        text = []

        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)

            print(f"Extracting text from {num_pages} pages...")

            for page_num in range(num_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                if page_text.strip():
                    text.append(f"=== Page {page_num + 1} ===\n{page_text}")

        return '\n\n'.join(text)

    async def translate_pdf(
        self,
        input_path: str,
        output_path: str,
        from_lang: str = "auto",
        to_lang: str = "Chinese"
    ):
        """Translate PDF file and save as text"""
        print(f"Reading PDF: {input_path}")
        text = self.extract_text_from_pdf(input_path)

        if not text.strip():
            print("No text extracted from PDF. The PDF might be image-based.")
            return

        print(f"Extracted {len(text)} characters")
        translated = await self.translate_text(text, from_lang, to_lang)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(translated)

        print(f"Translation saved to: {output_path}")
        if self.token_count_last:
            print(f"Used {self.token_count_last} tokens (Total: {self.token_count})")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description='DeepSeek Translator - Translate text, files, and PDFs')
    parser.add_argument('input', help='Input text or file path')
    parser.add_argument('-o', '--output', help='Output file path (required for file/PDF translation)')
    parser.add_argument('-f', '--from-lang', default='auto', help='Source language (default: auto)')
    parser.add_argument('-t', '--to-lang', default='Chinese', help='Target language (default: Chinese)')
    parser.add_argument('--file', action='store_true', help='Treat input as text file path')
    parser.add_argument('--pdf', action='store_true', help='Treat input as PDF file path')
    parser.add_argument('--context', help='Background on the source work (title, characters, setting): text, or path to a .txt file')
    parser.add_argument('--glossary', help='Glossary file in sakura (src->dst), galtransl or MIT format, see dict/')

    args = parser.parse_args()

    context = args.context
    if context and os.path.isfile(context):
        with open(context, encoding='utf-8') as f:
            context = f.read().strip()

    translator = DeepSeekTranslator(context=context, glossary_path=args.glossary)

    if args.pdf:
        if not args.output:
            print("Error: --output is required for PDF translation")
            return
        await translator.translate_pdf(args.input, args.output, args.from_lang, args.to_lang)
    elif args.file:
        if not args.output:
            print("Error: --output is required for file translation")
            return
        await translator.translate_file(args.input, args.output, args.from_lang, args.to_lang)
    else:
        result = await translator.translate_text(args.input, args.from_lang, args.to_lang)
        print("\n=== Translation ===")
        print(result)


if __name__ == '__main__':
    asyncio.run(main())
