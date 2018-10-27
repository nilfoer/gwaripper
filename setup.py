import setuptools

long_descr = """Script to rip audio files mainly from soundgasm.net but it also supports chirb.it and free
eraudica.com audios. Able to download single links or entire users. Links can also be obtained by scanning subs in
the subreddits gonewilaudio and pillowtalkaudio. Going through reddit is preferred since more post information can
be saved, if a selftext is present it will be saved alongside the audio file. Searching reddit and downloading
submissions by redditors is also supported. Saves the info of downloaded files as sqlite database but
also exports it to csv to be human-readable.

Call script with -h to show info of available commands!"""

setuptools.setup(
    name="GWARipper",
    version="0.1.0a1",
    description="A script that rips and downloads audio files from the gonewildaudio subreddit.",
    long_description=long_descr,
    url="",
    author="nilfoer",
    author_email="",
    license="",
    classifiers=[],
    keywords="script rip gonewildaudio download scraping",
    packages=setuptools.find_packages(exclude=['gwaripper.pyperclip', '*pyperclip', 'tests*']),
    install_requires=["1.5.25<=pyperclip<=1.7.0", "praw==6", "4.5.3<=bs4<=4.6.3"],
    package_data={
        'gwaripper': ['config.ini'],
    },
    entry_points={
        'console_scripts': [
            # linking the executable gwaripper here to running the python function main in the gwaripper module
            'gwaripper=gwaripper.gwaripper:main',
        ]}
)