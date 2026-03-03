# Contributing to Carrefour Egypt Scraper

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## 🚀 Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/alibadawi25/carrefour-scraper.git`
3. Create a feature branch: `git checkout -b feature/your-feature-name`
4. Make your changes
5. Test your changes thoroughly
6. Commit with clear messages: `git commit -m "Add: feature description"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Open a Pull Request

## 📝 Code Style

- Follow PEP 8 Python style guidelines
- Use type hints where appropriate
- Write docstrings for functions and classes
- Keep functions focused and single-purpose
- Maximum line length: 100 characters

### Code Formatting

```bash
# Install development dependencies
pip install black flake8 mypy

# Format code
black src/

# Lint code
flake8 src/

# Type check
mypy src/
```

## 🧪 Testing

- Add tests for new features
- Ensure all tests pass before submitting PR
- Test with both Arabic and English product pages
- Test error handling and edge cases

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=src tests/
```

## 🐛 Bug Reports

When reporting bugs, include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs or error messages
- Sample URLs (if applicable)

## ✨ Feature Requests

When requesting features:

- Describe the use case
- Explain why it would be valuable
- Suggest implementation approach (optional)
- Consider backwards compatibility

## 📊 Pull Request Guidelines

- Keep PRs focused on a single feature/fix
- Update README.md if adding new features
- Add/update tests for your changes
- Ensure all tests pass
- Update CHANGELOG.md
- Reference related issues

## 🎯 Priority Areas for Contribution

1. **Testing**: Add unit tests and integration tests
2. **Documentation**: Improve code comments and examples
3. **Performance**: Optimize scraping speed and memory usage
4. **Features**: See PROJECT_IDEAS.md for suggestions
5. **Error Handling**: Improve resilience and error messages

## 💡 Commit Message Format

```
Type: Brief description (50 chars max)

Detailed explanation if needed (wrap at 72 chars)

- Bullet points for multiple changes
- Reference issues: Fixes #123
```

**Types**: `Add`, `Fix`, `Update`, `Remove`, `Refactor`, `Docs`, `Test`

## 📞 Questions?

Feel free to open an issue for discussion before starting work on major changes.

---

**Thank you for contributing! 🙏**
