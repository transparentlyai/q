#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="q",
    version="0.6.1",
    description="A command Line AI Assistant",
    author="mauro@sauco.net",
    author_email="mauro@sauco.net",
    packages=find_packages(),
    py_modules=["q"],
    install_requires=[
        "anthropic>=0.18.0",
        "rich>=13.0.0",
        "prompt_toolkit>=3.0.0",
        "requests>=2.28.0",
        "beautifulsoup4>=4.11.0",
    ],
    entry_points={
        "console_scripts": [
            "q=q_cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
    ],
    python_requires=">=3.7",
)