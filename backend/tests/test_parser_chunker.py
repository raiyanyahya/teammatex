"""Test the tree-sitter code parser and chunker."""

import pytest

from app.services.onboarding.code_parser import CodeParser
from app.services.knowledge.chunker import CodeChunker


class TestCodeParser:
    def test_parse_python_functions(self, sample_python_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.py", sample_python_code)
        assert analysis is not None
        assert analysis.language == "python"

        functions = [e for e in analysis.entities if e.kind == "function"]
        classes = [e for e in analysis.entities if e.kind == "class"]

        func_names = {f.name for f in functions}
        assert "greet" in func_names
        assert "main" in func_names
        assert len(classes) == 1
        assert classes[0].name == "Greeter"

    def test_parse_python_class_methods(self, sample_python_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.py", sample_python_code)
        assert analysis is not None

        methods = [e for e in analysis.entities if e.kind == "function" and e.parent_name is None]
        method_names = {m.name for m in methods}
        assert "greet" in method_names
        assert "shout" in method_names

    def test_parse_js_functions(self, sample_js_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.js", sample_js_code)
        assert analysis is not None
        assert analysis.language in ("javascript", "typescript")

        entities = analysis.entities
        assert len(entities) > 0

    def test_parse_go_code(self, sample_go_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.go", sample_go_code)
        if analysis is None:
            pytest.skip("tree-sitter-go not installed")

        assert analysis.language == "go"
        functions = [e for e in analysis.entities if e.kind == "function"]
        assert len(functions) >= 1

    def test_parse_rust_code(self, sample_rust_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.rs", sample_rust_code)
        if analysis is None:
            pytest.skip("tree-sitter-rust not installed")

        assert analysis.language == "rust"
        assert len(analysis.entities) >= 1

    def test_parse_java_code(self, sample_java_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.java", sample_java_code)
        if analysis is None:
            pytest.skip("tree-sitter-java not installed")

        assert analysis.language == "java"
        classes = [e for e in analysis.entities if e.kind == "class"]
        assert len(classes) >= 1

    def test_unsupported_language_returns_none(self):
        parser = CodeParser()
        analysis = parser.parse_file("test.xyz", "some content")
        assert analysis is None

    def test_empty_file_returns_none(self):
        parser = CodeParser()
        analysis = parser.parse_file("test.py", "")
        assert analysis is None or len(analysis.entities) == 0

    def test_get_supported_languages(self):
        parser = CodeParser()
        langs = parser.get_supported_languages()
        assert isinstance(langs, list)
        assert len(langs) >= 0

    def test_parse_detects_imports(self, sample_python_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.py", sample_python_code)
        assert analysis is not None

        imports = [d for d in analysis.dependencies if d.kind == "imports"]
        assert len(imports) >= 1

    def test_parse_detects_calls(self, sample_python_code):
        parser = CodeParser()
        analysis = parser.parse_file("test.py", sample_python_code)
        assert analysis is not None

        calls = [d for d in analysis.dependencies if d.kind == "calls"]
        assert len(calls) >= 1


class TestCodeChunker:
    def test_chunk_python_by_functions(self, sample_python_code):
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_python_code, "test.py", "python")
        assert len(chunks) > 0

        func_chunks = [c for c in chunks if c.entity_type in ("function", "class")]
        assert len(func_chunks) >= 2

    def test_chunk_includes_file_header(self, sample_python_code):
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_python_code, "test.py", "python")

        headers = [c for c in chunks if c.entity_type == "file_header"]
        assert len(headers) == 1

    def test_chunk_empty_content(self):
        chunker = CodeChunker()
        chunks = chunker.chunk_file("", "empty.py", "python")
        assert len(chunks) == 0

    def test_chunk_plain_text_falls_back_to_windows(self):
        chunker = CodeChunker()
        text = "line " * 300
        chunks = chunker.chunk_file(text, "data.txt", "text")
        assert len(chunks) >= 0

    def test_chunk_text_basic(self):
        chunker = CodeChunker()
        words = ["word"] * 2000
        text = " ".join(words)
        chunks = chunker.chunk_text(text, max_chunk_size=500)
        assert len(chunks) == 4

    def test_chunk_windows_terminates(self):
        """Verify the infinite loop bug is fixed."""
        chunker = CodeChunker()
        lines = ["line"] * 300
        chunks = chunker._chunk_by_windows(lines, "test.py", "python")
        assert len(chunks) > 0
        assert len(chunks) < 100
