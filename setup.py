import setuptools
import os

with open("README.md", "r", encoding="UTF-8") as fh:
    long_description = fh.read()


webgui_data = []
for dirpath, dirnames, filenames in os.walk(os.path.abspath('gwaripper_webGUI')):
    try:
        dirnames.remove('__pycache__')
    except ValueError:
        pass
    for fn in filenames:
        if fn.endswith('.py'):
            continue
        webgui_data.append(os.path.join(dirpath, fn))


setuptools.setup(
    name="GWARipper",
    version="0.6.2",
    description="A script that downloads audio files from the gonewildaudio subreddit.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nilfoer/gwaripper",
    author="nilfoer",
    author_email="",
    license="MIT",
    keywords="script reddit gonewildaudio download scraping",
    packages=setuptools.find_packages(exclude=['tests*']),
    python_requires='>=3.6',
    install_requires=["pyperclip>=1.5.25,<=1.7.0", "praw>=7.5",
                      "beautifulsoup4>=4.5.3,<=4.6.3",
                      # 3.7.2 would be enough but mypy 0.782 uses >=3.7.4
                      "typing-extensions>=3.7.4"],

    tests_require=['pytest'],
    # using MANIFEST.in for these files does not seem to work!
    # non-python data that should be included in the pkg
    # mapping from package name to a list of relative (to package) path names that should be
    # copied into the package
    package_data={
        'gwaripper_webGUI': webgui_data,
        'gwaripper': 'migrations/*.py',
        },
    entry_points={
        'console_scripts': [
            # linking the executable gwaripper here to running the python
            # function main in the gwaripper module
            'gwaripper=gwaripper.cli:main',
            'gwaripper_webGUI=gwaripper_webGUI.start_webgui:main',
        ]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
