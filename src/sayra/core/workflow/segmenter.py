import re


class SentenceSegmenter:
    def __init__(self, min_chars: int, max_chars: int) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    def feed(self, delta: str) -> list[str]:
        self._buffer += delta
        output: list[str] = []
        while self._buffer:
            match = re.search(r"[.!?。！？；;]\s*", self._buffer)
            if match and match.end() >= self.min_chars:
                output.append(self._buffer[: match.end()].strip())
                self._buffer = self._buffer[match.end() :]
                continue
            if len(self._buffer) >= self.max_chars:
                split_at = self._buffer.rfind(" ", self.min_chars, self.max_chars)
                if split_at < self.min_chars:
                    split_at = self.max_chars
                output.append(self._buffer[:split_at].strip())
                self._buffer = self._buffer[split_at:]
                continue
            break
        return [part for part in output if part]

    def flush(self) -> str | None:
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining or None
