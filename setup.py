import setuptools

long_descr = """Script to rip audio files mainly from soundgasm.net but it also supports chirb.it and free
eraudica.com audios. Able download single links or entire users. Links can also be obtained by scanning subs in
the subreddits gonewilaudio and pillowtalkaudio. Going through reddits preferred since more post information can
be saved, if a selftext is present it will be saved alongside the audio file. Searching reddit and downloading
submissions by certain redditors is also supported. Saves the info of downloaded files in a csv and json file."""

setuptools.setup(
    name="GWARipper",
    version="0.1.0.dev1",
    description="A script that rips and downloads audio files from the gonewildaudio subreddit.",
    long_description=long_descr,
    url="",
    author="nilfoer",
    author_email="",
    license="",
    classifiers=[],
    keywords="script rip gonewildaudio download scraping",
    packages=setuptools.find_packages(exclude=['pyperclip', 'tests*']),
    install_requires=["pyperclip", "praw", "bs4", "pandas"],
    package_data={},
    entry_points={
        'console_scripts': [
            # linking the executable gwaripper here to running the python function main in the gwaripper module
            'gwaripper=gwaripper:main',
        ]}
)