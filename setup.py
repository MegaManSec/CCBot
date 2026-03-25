import os
import re
from setuptools import setup, find_packages

with open(os.path.join(os.path.dirname(__file__), "ccbot", "__init__.py")) as f:
    version = re.search(r'__version__\s*=\s*["\'](.+?)["\']', f.read()).group(1)

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="ccbot-py",
    version=version,
    author="Joshua Rogers",
    description="Chrome/Chromium Vulnerability Checker - monitors Chrome releases for CVEs and sends Slack notifications",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MegaManSec/CCBot",
    project_urls={
        "Homepage": "https://joshua.hu/ccbot-chrome-checker-bot-googlechromereleases-chromium-updates",
        "Author": "https://joshua.hu/",
        "Source": "https://github.com/MegaManSec/CCBot",
    },
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.32.3",
        "beautifulsoup4>=4.12.3",
        "feedparser>=6.0.11",
    ],
    entry_points={
        "console_scripts": [
            "ccbot=ccbot.ccbot:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Operating System :: OS Independent",
        "Topic :: Security",
        "Intended Audience :: System Administrators",
    ],
    license="AGPL-3.0",
)
