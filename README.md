# GWARipper
Script to download (mainly) audio files either by parsing reddit submissions for supported links or by directly downloading from soundgasm.net, eraudica.com etc. You can download single links, entire users or the top submissions of *gonewildaudio* of the last week. Going through reddit is preferred since more post information can
be saved, if a selftext is present it will be saved alongside the audio file. Searching reddit and downloading submissions by redditors is also supported. Saves the info of downloaded files in a SQLite database but also exports it to csv.

## GWARipper has a WebGUI too!

It supports rating and favoriting of audios, full-text-search, embedding files from your drive or the original source and more!

![GWARipper WebGUI Desktop](https://i.imgur.com/nLqPT5T.png)

## Download
You can either download the [bundled executable](https://github.com/nilfoer/gwaripper/releases) for Windows that has all the dependencies included. The exe will uncompress the bundled dependencies including data like HTML templates, into a temporary folder in your `APPDATA` folder e.g. `C:\Users\nilfoer\AppData\Local\Temp\_MEI175512`. If that is not what you want, use one of the other options!

Or you can download the [GWARipper-version.zip](https://github.com/nilfoer/gwaripper/releases) on the releases page (downloading the auto-generated source will not work if you want to use the webGUI, since static third-party files like fonts or bootstrap3 are not tracked by git!), unzip it and then install it using:
```
> python -m pip install .
```

Then you need to use `gwaripper` instead of `gwaripper.exe` and `gwaripper_webgui` instead of `gwaripper.exe webgui`.

If you don't want to install it to your python directory you can just unzip it and install the dependencies using:
```
> python -m pip install -r requirements.txt
```

Then you replace the `gwaripper` and `gwaripper_webgui` calls in the explanation below with `gwaripper-runner.py` and `gwaripper-runner.py webgui` respectively.

## Usage
### Setup
At the script's first run it will ask you to run it using the subcommand `config` to specfify the GWARipper root directory where all files will be downloaded to
```
> gwaripper.exe
root_path not set in gwaripper_config.ini, use command config -p 'C:\absolute\path' to specify where the files will be downloaded to
> gwaripper.exe config -p C:\Users\nilfoer\gwaripper
New root dir is: C:\Users\nilfoer\gwaripper
```
Using the `config` subcommand you can also specify other options like banned tags or set the frequency at which DB-backups are created. The config will be placed next to the executable or if you're using the source it will be inside the `gwaripper` directory.

#### API client IDs

GWARipper now comes pre-installed with a reddit and imgur client id but you can still get your own:

To get a client\_id you have to register an app at https://www.reddit.com/prefs/apps. The type should be *installed* or *script* (*installed* is enough, since we use read-only access).

If your app is of type *script* you also have to specify a client secret when setting the client id:
```
> gwaripper.exe config -rci fhkjHNA-348 -rcs 2ifk3458jklg
Successfully set Client ID
Successfully set Client Secret
```

To get an imgur client\_id you have to register an app at https://api.imgur.com/oauth2/addclient. And then set the client id using the `config` subcommand:
```
> gwaripper.exe config -ici fas8593-25afda389
Successfully set Imgur Client ID
```

### WebGUI
For using the WebGUI run the other entry point executable:
```
gwaripper.exe webgui
```
Then you can access the WebGUI by going to `localhost:7568` in your web browser. The first time you access the WebGUI you have to create a user by clicking on **Register**. Then just type in the username and password combination you chose and press **Login**.

To be able to access the site with e.g. your phone in your LAN use `gwaripper_webgui open` and then browse to http://INSERT.YOUR.IP.HERE:7568/

#### Searching
The search bar matches the input string against the entries reddit post title and the title on the host page by default (so it if there's a string without a preceeding keyword the title is searched).

Additionally you can search the following fields:

| Field                                 | search keyword |
| -------------------------------------:| --------------:|
| (Title and Reddit Title)              | title          |
| Host page (e.g. soundgasm) user       | artist         |
| OR Reddit user name                   |                |
| Reddit id                             | reddit\_id     |
| Reddit or Host page url               | url            |

All of these fields can be combined in one search. When the search string for a specific keyword contains spaces, it needs to be escaped with quotes. To search for multiple items that have to be present, separate them with semicolons. Everything but the title requires exact (case-sensitive as well) matches!

Searching the title uses SQLite full-text-search:
- "monster girl" searches for 'monster' and 'girl' keywords being in the row
- "monster + girl" searches for 'monster girl' phrase being in the row
- You can use an asterisk(\*) to match any keyword that starts with that phrase (keyword can't start with an asterisk). E.g.: hypno\* matches Hypno, Hypnotic, Hypnosis, etc.
- You can use the Boolean operators NOT, OR, or AND (operators **must** be in uppercase) to combine queries:
    - q1 AND q2: matches if both q1 and q2 queries match.
    - q1 OR q2: matches if either query q1 or q2 matches.
    - q1 NOT q2: matches if query q1 matches and q2 doesn’t match.
- To change the operator precedence, you use parentheses to group expressions.
- Special characters mentioned here are the only ones allowed in the title search query!
- Normally double-quotes(**"**) would be allowed but due to the way we're currently parsing the search query they're not!
- For more information see: [SQLite.org: Full-text Query Syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax)

E.g. this string searches for audios by sassmastah77 (as reddit user or as author on an audio-host like soundgasm.net) with GFE in the title
```
artist:sassmastah77 GFE
```

Search for 'monster girl' or 'demon girl' being in the title:
```
(monster + girl) OR (demon + girl)
```

### Examples
#### Example: Watch for copied reddit urls and parse them from downloadable files
Run script from command line like so:
```
> gwaripper watch
```
To watch supported URLs in your clipboard.

Press CTRL+C to stop watching. The urls will be saved in a text file the GWARipper\_root/_linkcol folder. You then will be asked if you want to download/parse the found URLs.

#### Example: Searching a subreddit
You can search a subreddit for submissions using the [lucene search syntax](https://www.reddit.com/wiki/search), e.g.:
```
> gwaripper search pillowtalkaudio "[comfort] nsfw:no" 5 -t all
```
Searches in r/pillowtalkaudio for the 5 most relevant submissions, that have comfort tag, nsfw results are excluded and it searches in time-range *all*. The found submissions will be searched for audios and thos will then be downloaded.

### Help
Call script with -h to show info of all available commands!
