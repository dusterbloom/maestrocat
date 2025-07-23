from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="maestrocat",
    version="0.1.0",
    author="MaestroCat Team",
    description="A Pipecat extension for building local voice agents with enhanced debugging and modularity",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dusterbloom/maestrocat",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "pipecat-ai>=0.0.27",
        "websockets>=11.0",
        "httpx>=0.25.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0",
        "numpy>=1.24.0",
        "aiohttp>=3.9.0",
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "python-dotenv>=0.21.0",
    ],
    extras_require={
        "whisperlive": ["pyaudio>=0.2.11"],
        "debug": ["prometheus-client>=0.18.0", "psutil>=5.9.0"],
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
        "all": [
            "pyaudio>=0.2.11",
            "prometheus-client>=0.18.0",
            "psutil>=5.9.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "maestrocat=maestrocat.cli:main",
            "maestrocat-debug=maestrocat.apps.debug_ui:main",
        ],
    },
)