import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# Override settings for testing
os.environ.setdefault("TEAMMATEX_SECRET_KEY", "test-secret-key-for-testing-only-minimum-16")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "teammatex_test")
os.environ.setdefault("POSTGRES_USER", "teammatex")
os.environ.setdefault("POSTGRES_PASSWORD", "teammatex_test")
os.environ.setdefault("NEO4J_PASSWORD", "neo4j_test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")


@pytest.fixture(scope="session")
def sqlite_engine():
    """In-memory SQLite engine for model tests (no Postgres needed)."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    return engine


@pytest.fixture(scope="session")
def sqlite_session(sqlite_engine):
    """Create all tables and return a session factory."""
    from app.models.base import Base
    Base.metadata.create_all(sqlite_engine)
    Session = sessionmaker(bind=sqlite_engine)
    return Session


@pytest.fixture
def db_session(sqlite_session):
    """Per-test database session with automatic rollback."""
    session = sqlite_session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_python_code():
    return '''"""Sample module for testing."""

import os
from typing import Optional


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"


class Greeter:
    """A class that greets people."""

    def __init__(self, prefix: str = "Hello"):
        self.prefix = prefix

    def greet(self, name: str) -> str:
        return f"{self.prefix}, {name}!"

    def shout(self, name: str, times: int = 1) -> str:
        msg = self.greet(name)
        return msg.upper() * times


def main():
    g = Greeter("Hi")
    print(g.greet("World"))


if __name__ == "__main__":
    main()
'''


@pytest.fixture
def sample_js_code():
    return '''// Sample JavaScript module

/**
 * Return a greeting.
 * @param {string} name
 * @returns {string}
 */
function greet(name) {
    return `Hello, ${name}!`;
}

class Greeter {
    constructor(prefix = "Hello") {
        this.prefix = prefix;
    }

    greet(name) {
        return `${this.prefix}, ${name}!`;
    }

    shout(name, times = 1) {
        const msg = this.greet(name);
        return msg.toUpperCase().repeat(times);
    }
}

function main() {
    const g = new Greeter("Hi");
    console.log(g.greet("World"));
}

module.exports = { greet, Greeter, main };
'''


@pytest.fixture
def sample_go_code():
    return '''package main

import "fmt"

// Greet returns a greeting.
func Greet(name string) string {
    return fmt.Sprintf("Hello, %s!", name)
}

type Greeter struct {
    Prefix string
}

func (g *Greeter) Greet(name string) string {
    return fmt.Sprintf("%s, %s!", g.Prefix, name)
}

func main() {
    g := &Greeter{Prefix: "Hi"}
    fmt.Println(g.Greet("World"))
}
'''


@pytest.fixture
def sample_rust_code():
    return '''/// Sample Rust module

/// Return a greeting.
pub fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

pub struct Greeter {
    prefix: String,
}

impl Greeter {
    pub fn new(prefix: &str) -> Self {
        Greeter { prefix: prefix.to_string() }
    }

    pub fn greet(&self, name: &str) -> String {
        format!("{}, {}!", self.prefix, name)
    }

    pub fn shout(&self, name: &str, times: usize) -> String {
        let msg = self.greet(name);
        msg.to_uppercase().repeat(times)
    }
}

fn main() {
    let g = Greeter::new("Hi");
    println!("{}", g.greet("World"));
}
'''


@pytest.fixture
def sample_java_code():
    return '''package com.example;

/**
 * Sample Java module.
 */
public class Greeter {
    private String prefix;

    public Greeter(String prefix) {
        this.prefix = prefix;
    }

    public Greeter() {
        this("Hello");
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }

    public String shout(String name, int times) {
        StringBuilder sb = new StringBuilder();
        String msg = greet(name);
        for (int i = 0; i < times; i++) {
            sb.append(msg.toUpperCase());
        }
        return sb.toString();
    }

    public static void main(String[] args) {
        Greeter g = new Greeter("Hi");
        System.out.println(g.greet("World"));
    }
}
'''


@pytest.fixture
def tmp_repo_dir(tmp_path):
    """Create a temporary directory structure mimicking a git repo."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / ".git").mkdir()

    py_file = repo / "src" / "main.py"
    py_file.write_text('''"""Main module."""

def process(data: list[int]) -> int:
    """Process data and return the sum."""
    return sum(data)

def validate_input(value: str) -> bool:
    """Validate user input."""
    return len(value) > 0 and value.isalnum()

class DataProcessor:
    def __init__(self, multiplier: int = 1):
        self.multiplier = multiplier

    def process(self, data: list[int]) -> int:
        return sum(data) * self.multiplier
''')

    test_file = repo / "tests" / "test_main.py"
    test_file.write_text('''"""Tests for main module."""

import pytest
from src.main import process, DataProcessor

def test_process():
    assert process([1, 2, 3]) == 6

def test_data_processor():
    dp = DataProcessor(2)
    assert dp.process([1, 2, 3]) == 12
''')

    js_file = repo / "src" / "utils.js"
    js_file.write_text('''// Utility functions

/**
 * Process data and return the sum.
 */
function processData(data) {
    return data.reduce((a, b) => a + b, 0);
}

function validateInput(value) {
    return value && value.length > 0 && /^[a-zA-Z0-9]+$/.test(value);
}

module.exports = { processData, validateInput };
''')

    return repo
