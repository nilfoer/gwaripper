# GWARipper
Script to download audio files either by parsing reddit submissions for supported links or by directly downloading from soundgasm.net or eraudica.com (for free audios). It is able to download single links or entire users. Going through reddit is preferred since more post information can
be saved, if a selftext is present it will be saved alongside the audio file. Searching reddit and downloading submissions by redditors is also supported. Saves the info of downloaded files in a SQLite database but also exports it to csv.

## Usage
### Setup
At the script's first run it will ask you to run it using the subcommand `config` to setup the GWARipper_root directory
```
> gwaripper-runner.py
root_path not set in config.ini, use command config -p 'C:\absolute\path' to specify where the files will be downloaded to
> gwaripper-runner.py config -p C:\Users\nilfoer\gwaripper
New root dir is: C:\Users\nilfoer\gwaripper
```
Using the `config` subcommand you can also specify other options like banned tags or set the frequency at which DB-backups are created.

To be able to use GWARipper's reddit functionalities you have to specify a reddit client_id. To get a client_id you have to register an app at https://www.reddit.com/prefs/apps. The type should be *installed* or *script* (*installed* is enough, since we use read-only access).

If your app is of type *script* you also have to specify a client secret when setting the client id:
```
> gwaripper-runner.py config -ci fhkjHNA-348 -cs 2ifk3458jklg
Successfully set Client ID
Successfully set Client Secret
```

To be able to automatically download found imgur images and albums (direct links always work) you have to set the imgur client id. To get a client_id you have to register an app at https://api.imgur.com/oauth2/addclient. And then set the client id using the `config` subcommand:
```
> gwaripper-runner.py config -ici fas8593-25afda389
Successfully set Imgur Client ID
```
Now you're ready to use GWARipper!

### Examples
#### Example: Watch for copied reddit urls and parse them from downloadable files
Run script from command line like so:
```
> gwaripper-runner.py watch r
```
To watch for reddit submission URLs in your clipboard.

Press CTRL+C to stop watching. The urls will be saved in a text file the GWARipper_root/_linkcol folder. You then will be asked if you want to download/parse the found URLs.

#### Example: Searching a subreddit
You can search a subreddit for submissions using the [lucene search syntax](https://www.reddit.com/wiki/search), e.g.:
```
> gwaripper-runner.py search pillowtalkaudio "[comfort] nsfw:no" 5 -t all
```
Searches in r/pillowtalkaudio for the 5 most relevant submissions, that have comfort tag, nsfw results are excluded and it searches in time-range *all*. The found submissions will be searched for audios and thos will then be downloaded.

### Help
Call script with -h to show info of all available commands!