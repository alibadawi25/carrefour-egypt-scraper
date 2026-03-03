"""Setup configuration for Carrefour Egypt Scraper."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="carrefour-scraper",
    version="1.0.0",
    author="Ali Badawi",
    author_email="alibadawi25@gmail.com",
    description="Intelligent bilingual web scraper for Carrefour Egypt products",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/alibadawi25/carrefour-egypt-scraper",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "apify>=2.7.3",
        "crawlee[playwright]>=0.6.12",
        "beautifulsoup4>=4.12.0",
        "lxml>=4.9.0",
        "httpx>=0.25.0",
        "cachetools>=5.3.0",
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.5.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "carrefour-scraper=src.main:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
