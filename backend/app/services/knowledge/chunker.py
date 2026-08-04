from dataclasses import dataclass

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class CodeChunk:
    text: str
    file_path: str
    start_line: int
    end_line: int
    entity_type: str  # function, class, file_header, comment_block
    language: str
    entity_name: str | None = None


class CodeChunker:
    MAX_CHUNK_TOKENS = 1000
    OVERLAP_TOKENS = 100

    def chunk_file(self, content: str, file_path: str, language: str) -> list[CodeChunk]:
        lines = content.splitlines()
        if not lines:
            return []

        chunks: list[CodeChunk] = []

        # Try structured chunking by functions first
        func_chunks = self._chunk_by_functions(content, file_path, language, lines)
        if func_chunks:
            chunks.extend(func_chunks)
        else:
            # Fall back to fixed-size windows
            chunks.extend(self._chunk_by_windows(lines, file_path, language))

        # Add file header as metadata chunk
        header = self._extract_header(content, file_path, language, lines)
        if header:
            chunks.append(header)

        return chunks

    def _chunk_by_functions(
        self, content: str, file_path: str, language: str, lines: list[str]
    ) -> list[CodeChunk]:
        from app.services.onboarding.code_parser import CodeParser

        parser = CodeParser()
        analysis = parser.parse_file(file_path, content)

        if not analysis or not analysis.entities:
            return []

        chunks: list[CodeChunk] = []
        funcs = [e for e in analysis.entities if e.kind == "function"]
        classes = [e for e in analysis.entities if e.kind == "class"]

        for entity in funcs + classes:
            start = max(0, entity.start_line - 1)
            end = min(len(lines), entity.end_line)
            chunk_lines = lines[start:end]
            chunk_text = "\n".join(chunk_lines)

            if len(chunk_text) > self.MAX_CHUNK_TOKENS * 4:
                sub_chunks = self._chunk_by_windows(chunk_lines, file_path, language, start)
                chunks.extend(sub_chunks)
            else:
                chunks.append(
                    CodeChunk(
                        text=chunk_text,
                        file_path=file_path,
                        start_line=entity.start_line,
                        end_line=entity.end_line,
                        entity_type=entity.kind,
                        language=language,
                        entity_name=entity.name,
                    )
                )

        return chunks

    def _chunk_by_windows(
        self, lines: list[str], file_path: str, language: str, line_offset: int = 0
    ) -> list[CodeChunk]:
        chunks: list[CodeChunk] = []
        chunk_size = max(1, self.MAX_CHUNK_TOKENS // 4)
        overlap = max(0, self.OVERLAP_TOKENS // 4)
        i = 0
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end]
            chunks.append(
                CodeChunk(
                    text="\n".join(chunk_lines),
                    file_path=file_path,
                    start_line=line_offset + i + 1,
                    end_line=line_offset + end,
                    entity_type="window",
                    language=language,
                )
            )
            if end >= len(lines):
                break
            i = end - overlap
            if i <= 0:
                i = end
        return chunks

    def _extract_header(
        self, content: str, file_path: str, language: str, lines: list[str]
    ) -> CodeChunk | None:
        header_lines = lines[:20]
        header_text = "\n".join(header_lines)
        return CodeChunk(
            text=header_text,
            file_path=file_path,
            start_line=1,
            end_line=min(20, len(lines)),
            entity_type="file_header",
            language=language,
        )

    def chunk_text(self, text: str, max_chunk_size: int = 1000) -> list[str]:
        words = text.split()
        chunks: list[str] = []
        for i in range(0, len(words), max_chunk_size):
            chunk = " ".join(words[i : i + max_chunk_size])
            chunks.append(chunk)
        return chunks
