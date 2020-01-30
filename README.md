# GWARipper
Script to download audio files either by parsing reddit submissions for supported links or by directly downloading from soundgasm.net or eraudica.com (for free audios). It is able to download single links or entire users. Going through reddit is preferred since more post information can
be saved, if a selftext is present it will be saved alongside the audio file. Searching reddit and downloading submissions by redditors is also supported. Saves the info of downloaded files in a SQLite database but also exports it to csv.

## Download
You can either download the [source](https://github.com/nilfoer/gwaripper/archive/master.zip) and install it using:
```
> python -m pip install .
```
Or you can download the [single-folder-install]() that has all the dependencies included.

## Usage
### Setup
At the script's first run it will ask you to run it using the subcommand `config` to setup the GWARipper_root directory
```
> gwaripper
root_path not set in gwaripper_config.ini, use command config -p 'C:\absolute\path' to specify where the files will be downloaded to
> gwaripper config -p C:\Users\nilfoer\gwaripper
New root dir is: C:\Users\nilfoer\gwaripper
```
Using the `config` subcommand you can also specify other options like banned tags or set the frequency at which DB-backups are created.

To be able to use GWARipper's reddit functionalities you have to specify a reddit client_id. To get a client_id you have to register an app at https://www.reddit.com/prefs/apps. The type should be *installed* or *script* (*installed* is enough, since we use read-only access).

If your app is of type *script* you also have to specify a client secret when setting the client id:
```
> gwaripper config -ci fhkjHNA-348 -cs 2ifk3458jklg
Successfully set Client ID
Successfully set Client Secret
```

To be able to automatically download found imgur images and albums (direct links always work) you have to set the imgur client id. To get a client_id you have to register an app at https://api.imgur.com/oauth2/addclient. And then set the client id using the `config` subcommand:
```
> gwaripper config -ici fas8593-25afda389
Successfully set Imgur Client ID
```
Now you're ready to use GWARipper!

### WebGUI
For using the WebGUI run the script like so:
```
gwaripper-runner.py webgui
```
Then you can access the WebGUI by going to `localhost:7568` in your web browser. The first time you access the WebGUI you have to create a user by clicking on **Register**. Then just type in the username and password combination you chose and press **Login**.

To be able to access the site with e.g. your phone in your LAN use `gwaripper-runner.py webgui open` and then browse to http://INSERT.YOUR.IP.HERE:7568/

#### Searching
The search bar matches the input string against the entries reddit post title and the title on the host page by default (so it if there's a string without a preceeding keyword the title is searched).

Additionally you can search the following fields:

| Field                                 | search keyword |
| -------------------------------------:| --------------:|
| (Title)                               | title          |
| Host page (e.g. soundgasm) user       | sgasm\_user    |
| Reddit user name                      | reddit\_user   |
| Reddit id                             | reddit\_id     |
| Reddit url                            | reddit\_url    |
| Host page URL                         | url            |

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

E.g. this string searches for audios by sassmastah77 with GFE in the title
```
sgasm_user:sassmastah77 GFE
```

Search for 'monster girl' or 'demon girl' being in the title:
```
(monster + girl) OR (demon + girl)
```

### Examples
#### Example: Watch for copied reddit urls and parse them from downloadable files
Run script from command line like so:
```
> gwaripper watch r
```
To watch for reddit submission URLs in your clipboard.

Press CTRL+C to stop watching. The urls will be saved in a text file the GWARipper_root/_linkcol folder. You then will be asked if you want to download/parse the found URLs.

#### Example: Searching a subreddit
You can search a subreddit for submissions using the [lucene search syntax](https://www.reddit.com/wiki/search), e.g.:
```
> gwaripper search pillowtalkaudio "[comfort] nsfw:no" 5 -t all
```
Searches in r/pillowtalkaudio for the 5 most relevant submissions, that have comfort tag, nsfw results are excluded and it searches in time-range *all*. The found submissions will be searched for audios and thos will then be downloaded.

### Help
Call script with -h to show info of all available commands!
