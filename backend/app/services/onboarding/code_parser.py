from dataclasses import dataclass, field
from pathlib import Path

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class CodeEntity:
    name: str
    kind: str  # function, class, method, interface, type, variable
    file_path: str
    start_line: int
    end_line: int
    language: str
    parent_name: str | None = None
    signature: str | None = None
    docstring: str | None = None
    role: str = "production"  # production, test, fixture, generated, config


@dataclass
class Dependency:
    source: str  # "file_path:entity_name"
    target: str  # "file_path:entity_name"
    kind: str  # imports, calls, extends, implements


@dataclass
class FileAnalysis:
    file_path: str
    language: str
    entities: list[CodeEntity] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    lines: int = 0


class CodeParser:
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript_tsx",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
    }

    SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "go", "rust", "java"}

    def __init__(self) -> None:
        self._parsers: dict[str, object] = {}
        self._init_parsers()

    def _init_parsers(self) -> None:
        import tree_sitter

        def _make_parser(lang_fn):
            try:
                lang = lang_fn()
                if isinstance(lang, tree_sitter.Language):
                    return tree_sitter.Parser(lang)
                return tree_sitter.Parser(tree_sitter.Language(lang))
            except Exception:
                return None

        try:
            import tree_sitter_javascript
            import tree_sitter_python

            try:
                import tree_sitter_typescript
            except ImportError:
                tree_sitter_typescript = None

            try:
                import tree_sitter_go
            except ImportError:
                tree_sitter_go = None

            try:
                import tree_sitter_rust
            except ImportError:
                tree_sitter_rust = None

            try:
                import tree_sitter_java
            except ImportError:
                tree_sitter_java = None

        except ImportError as e:
            logger.warning("tree_sitter_not_available", error=str(e))
            return

        self._parsers["python"] = _make_parser(tree_sitter_python.language)
        self._parsers["javascript"] = _make_parser(tree_sitter_javascript.language)

        if tree_sitter_typescript:
            self._parsers["typescript"] = _make_parser(tree_sitter_typescript.language_typescript)
            self._parsers["typescript_tsx"] = _make_parser(tree_sitter_typescript.language_tsx)

        if tree_sitter_go:
            self._parsers["go"] = _make_parser(tree_sitter_go.language)

        if tree_sitter_rust:
            self._parsers["rust"] = _make_parser(tree_sitter_rust.language)

        if tree_sitter_java:
            self._parsers["java"] = _make_parser(tree_sitter_java.language)

        failed = [k for k, v in self._parsers.items() if v is None]
        for k in failed:
            logger.warning(f"tree_sitter_{k}_parser_failed")
            del self._parsers[k]

    def parse_file(self, file_path: str, content: str | None = None) -> FileAnalysis | None:
        ext = Path(file_path).suffix.lower()
        language = self.LANGUAGE_MAP.get(ext)
        if not language or language not in self._parsers:
            return None

        try:
            if content is None:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
        except Exception:
            return None

        parser_lang = language
        if parser_lang not in self._parsers:
            if ext in (".tsx", ".jsx"):
                parser_lang = "javascript"
            else:
                return None

        analysis = FileAnalysis(
            file_path=file_path,
            language=language,
            lines=len(content.splitlines()),
        )

        try:
            parser = self._parsers[parser_lang]
            tree = parser.parse(content.encode())
            root = tree.root_node
            self._walk_tree(root, content, analysis, language)
        except Exception as e:
            logger.debug("parse_error", file=file_path, error=str(e))

        return analysis

    # Call-expression node types per grammar: Python `call`; JS/TS/Go/Rust
    # `call_expression`; Java `method_invocation`. (We only checked
    # `call_expression`, so Python calls were never detected.)
    _CALL_NODES = ("call", "call_expression", "method_invocation")

    def _walk_tree(
        self,
        node,
        source: str,
        analysis: FileAnalysis,
        language: str,
        depth: int = 0,
        enclosing_fn: str | None = None,
    ) -> None:
        if depth > 500:
            return
        node_fn = enclosing_fn
        if node.type in ("function_definition", "function_declaration", "method_definition"):
            entity = self._extract_function(node, source, analysis.file_path, language)
            analysis.entities.append(entity)
            # Attribute calls inside this subtree to this function (the caller).
            node_fn = entity.name
        elif node.type in ("class_definition", "class_declaration"):
            analysis.entities.append(
                self._extract_class(node, source, analysis.file_path, language)
            )
        elif node.type == "import_statement" or node.type == "import_declaration":
            dep = self._extract_import(node, source, analysis.file_path, language)
            if dep:
                analysis.dependencies.append(dep)
        elif node.type in self._CALL_NODES:
            dep = self._extract_call(node, source, analysis.file_path, language, enclosing_fn)
            if dep:
                analysis.dependencies.append(dep)

        for child in node.children:
            self._walk_tree(child, source, analysis, language, depth + 1, node_fn)

    def _extract_function(self, node, source: str, file_path: str, language: str) -> CodeEntity:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode() if name_node else "anonymous"
        body = node.child_by_field_name("body")
        end_line = body.end_point[0] + 1 if body else node.end_point[0] + 1

        signature = source[node.start_byte : node.end_byte].split("{")[0].strip()[:200]
        docstring = self._extract_docstring(node, source)

        return CodeEntity(
            name=name,
            kind="function",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=end_line,
            language=language,
            signature=signature,
            docstring=docstring,
        )

    def _extract_class(self, node, source: str, file_path: str, language: str) -> CodeEntity:
        name_node = node.child_by_field_name("name")
        name = name_node.text.decode() if name_node else "anonymous"
        docstring = self._extract_docstring(node, source)

        return CodeEntity(
            name=name,
            kind="class",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            language=language,
            docstring=docstring,
        )

    def _extract_docstring(self, node, source: str) -> str | None:
        for child in node.children:
            if child.type in ("block_comment", "comment", "doc_comment", "line_comment"):
                return child.text.decode()[:500]
            if child.type == "expression_statement":
                inner = child.child(0) if child.child_count > 0 else None
                if inner and inner.type == "string":
                    return inner.text.decode()[:500]
        return None

    def _extract_import(
        self, node, source: str, file_path: str, language: str
    ) -> Dependency | None:
        text = source[node.start_byte : node.end_byte]
        target = text.strip()[:200]
        return Dependency(
            source=file_path,
            target=target,
            kind="imports",
        )

    def _extract_call(
        self, node, source: str, file_path: str, language: str, enclosing_fn: str | None = None
    ) -> Dependency | None:
        # `function` field: Python/JS/TS/Go/Rust; `name` field: Java method_invocation.
        func_node = node.child_by_field_name("function") or node.child_by_field_name("name")
        if func_node:
            name = func_node.text.decode()[:100]
            # source is the CALLER function name so the graph builder can match it
            # to a Function node; falls back to the file for module-level calls
            # (which have no caller node and so won't create an edge).
            return Dependency(
                source=enclosing_fn or file_path,
                target=name,
                kind="calls",
            )
        return None

    def get_supported_languages(self) -> list[str]:
        return sorted(self._parsers.keys())
