PRAGMA foreign_keys=off;
BEGIN TRANSACTION;
CREATE TABLE Alias(
                    id INTEGER PRIMARY KEY ASC,
                    artist_id INTEGER,
                    name TEXT UNIQUE NOT NULL,
                    FOREIGN KEY (artist_id) REFERENCES Artist(id)
                        ON DELETE RESTRICT
                );
CREATE TABLE Artist(
                    id INTEGER PRIMARY KEY ASC,
                    name TEXT UNIQUE NOT NULL
                );
CREATE TABLE AudioFile(
                    id INTEGER PRIMARY KEY ASC,
                    collection_id INTEGER,
                    date DATE NOT NULL,
                    description TEXT,
                    filename TEXT NOT NULL,
                    title TEXT,
                    url TEXT UNIQUE NOT NULL,
                    alias_id INTEGER NOT NULL,
                    rating REAL,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (collection_id) REFERENCES FileCollection(id)
                      -- can't delete a FileCollection if there are still rows with
                      -- it's id as collection_id here
                      ON DELETE RESTRICT,
                    FOREIGN KEY (alias_id) REFERENCES Alias(id)
                      ON DELETE RESTRICT
                );
CREATE TABLE FileCollection(
                    id INTEGER PRIMARY KEY ASC,
                    url TEXT UNIQUE NOT NULL,
                    id_on_page TEXT,
                    title TEXT,
                    subpath TEXT NOT NULL,
                    reddit_info_id INTEGER,
                    parent_id INTEGER,
                    alias_id INTEGER NOT NULL,
                    FOREIGN KEY (reddit_info_id) REFERENCES "RedditInfo"(id)
                      ON DELETE RESTRICT,
                    FOREIGN KEY (parent_id) REFERENCES FileCollection(id)
                      ON DELETE RESTRICT,
                    FOREIGN KEY (alias_id) REFERENCES Alias(id)
                      ON DELETE RESTRICT
                );
CREATE TABLE Flair(
            id INTEGER PRIMARY KEY ASC,
            name TEXT UNIQUE NOT NULL
        );
CREATE TABLE GWAR_Version (
                    version_id INTEGER PRIMARY KEY ASC,
                    dirty INTEGER NOT NULL
                );
CREATE TABLE ListenLater (
          id INTEGER PRIMARY KEY ASC,
          audio_id INTEGER,
          FOREIGN KEY (audio_id) REFERENCES AudioFile(id)
            ON DELETE CASCADE
        );
CREATE TABLE "RedditInfo"(
            id INTEGER PRIMARY KEY ASC,
            created_utc REAL,
            upvotes INTEGER,
            flair_id INTEGER,
            selftext TEXT,
            FOREIGN KEY (flair_id) REFERENCES Flair(id)
              ON DELETE RESTRICT
        );
CREATE VIRTUAL TABLE Titles_fts_idx USING fts5(
          audio_title, collection_title,
          content='v_audio_and_collection_titles',
          content_rowid='audio_id');
CREATE VIEW v_audio_and_collection_combined
        AS
        SELECT
            AudioFile.id,
            AudioFile.collection_id,
            AudioFile.date,
            AudioFile.description,
            AudioFile.filename,
            AudioFile.title,
            AudioFile.url,
            AudioFile.alias_id,
            AudioFile.rating,
            AudioFile.favorite,
            Alias.name as alias_name,
            Artist.name as artist_name,
            FileCollection.id as fcol_id,
            FileCollection.url as fcol_url,
            FileCollection.id_on_page as fcol_id_on_page,
            FileCollection.title as fcol_title,
            FileCollection.subpath as fcol_subpath,
            FileCollection.reddit_info_id as fcol_reddit_info_id,
            FileCollection.parent_id as fcol_parent_id,
            FileCollection.alias_id as fcol_alias_id,
            -- get alias name for FileCollection
            -- artist_id of fcol and audiofile will be the same so we don't
            -- have to query for that
            (SELECT
                    Alias.name
             FROM Alias WHERE Alias.id = FileCollection.alias_id) as fcol_alias_name,
            RedditInfo.created_utc as reddit_created_utc,
            Flair.name as reddit_flair,
            EXISTS (SELECT 1 FROM ListenLater WHERE audio_id = AudioFile.id) as listen_later
        FROM AudioFile
        LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id
        LEFT JOIN RedditInfo ON FileCollection.reddit_info_id = RedditInfo.id
        LEFT JOIN Flair ON RedditInfo.flair_id = Flair.id
        JOIN Alias ON Alias.id = AudioFile.alias_id
        LEFT JOIN Artist ON Artist.id = Alias.artist_id;
CREATE VIEW v_audio_and_collection_titles
                AS
                SELECT
                    AudioFile.id as audio_id,
                    FileCollection.title as collection_title,
                    AudioFile.title as audio_title
                FROM AudioFile
                LEFT JOIN FileCollection ON AudioFile.collection_id = FileCollection.id;
INSERT INTO "Alias" VALUES
(1,NULL,'deleted_users'),
(2,NULL,'_unknown_user_files'),
(3,1,'skitty-gwa'),
(4,1,'skitty'),
(5,2,'sassmastah77');
INSERT INTO "Artist" VALUES
(1,'skitty-gwa'),
(2,'sassmastah77');
INSERT INTO "AudioFile" VALUES
(1,1,'2020-11-13','[F4M] [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breast play] [Outercourse] [Handjob] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [Script: BowTieGuy]','02_Motherly Moth Girl Keeps You Warm [F4M].m4a','Motherly Moth Girl Keeps You Warm [F4M]','https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4M',4,NULL,0),
(2,1,'2020-11-13','[F4F] [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breast play] [Outercourse] [Fingering] [Cozy blanket] [Kissing] [Cunnilingus] [Two orgasms] [Clit play] [Pinning you down] [Wrapped in wings] [Aftercare] [ASMR] [Script: BowTieGuy]','03_Motherly Moth Girl Keeps You Warm [F4F].m4a','Motherly Moth Girl Keeps You Warm [F4F]','https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4F',4,NULL,0),
(3,1,'2020-11-13','[F4TF] [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breast play] [Outercourse] [Handjob] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [Script: BowTieGuy]','04_Motherly Moth Girl Keeps You Warm [F4TF].m4a','Motherly Moth Girl Keeps You Warm [F4TF]','https://soundgasm.net/u/skitty/Motherly-Moth-Girl-Keeps-You-Warm-F4TF',4,NULL,0),
(4,NULL,'2020-11-13',NULL,'Lonely Kitty.mp3','Lonely Kitty','https://chirb.it/F5hInh',4,NULL,0),
(5,2,'2020-11-13','[MILF] [comforted by your ex''s sweet + sexy mom] [realistic slow build] [kissing] [sloppy wet handjob] [cock worshipping, deep-throating blowjob] [just use my mouth to make yourself feel good] [dirty talk] [sucking my big tits] [riding you on the couch] [creampie] [tasting myself on your dick] [improv] [43 mins]','[F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help _F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help You Feel Better.m4a','F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help You Feel Better','https://soundgasm.net/u/sassmastah77/F4M-My-Daughter-is-an-Idiot-for-Breaking-Up-With-You-Let-Me-Help-You-Feel-Better',5,NULL,0),
(6,NULL,'2020-11-13','[your older female cousin] [friends to lovers] [teasing] [tickling] [giggles] [perv encouragement] [kissing] [big tits] [dirty talk] [whispers] [blowjob] [licking, sucking + face-fucking] [rubbing my clit while deep-throating your cock] [begging for your cum] [27 mins]','[f4m] Your Favourite Cousin.m4a','[f4m] Your Favourite Cousin','https://soundgasm.net/u/sassmastah77/f4m-Your-Favourite-Cousin-1',5,NULL,0);
INSERT INTO "FileCollection" VALUES
(1,'https://www.reddit.com/r/gonewildaudio/comments/ix81f7/f4m_f4f_f4tf_motherly_moth_girl_keeps_you_warm/','ix81f7','[F4M] / [F4F] / [F4TF] Motherly Moth Girl Keeps You Warm [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breastplay] [Outercourse] [Handjob/fingering] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [25min+] [Script: BowTieGuy_GWA]','[F4M] _ [F4F] _ [F4TF] Motherly Moth Girl Keeps You Warm [Gentle Fdom]',1,NULL,3),
(2,'https://www.reddit.com/r/gonewildaudio/comments/6dvum7/f4m_my_daughter_is_an_idiot_for_breaking_up_with/','6dvum7','[F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help You Feel Better [milf] [sex with your ex''s sweet + sexy mom] [realistic slow build] [kissing] [sloppy wet handjob + deep-throating blowjob] [dirty talk] [sucking my big tits] [riding you on the couch] [creampie] [improv]','',2,NULL,5);
INSERT INTO "GWAR_Version" VALUES
(4,0);
INSERT INTO "RedditInfo" VALUES
(1,1600718407.0,NULL,NULL,NULL),
(2,1496001999.0,NULL,NULL,NULL);
INSERT INTO "Titles_fts_idx" VALUES
('Motherly Moth Girl Keeps You Warm [F4M]','[F4M] / [F4F] / [F4TF] Motherly Moth Girl Keeps You Warm [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breastplay] [Outercourse] [Handjob/fingering] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [25min+] [Script: BowTieGuy_GWA]'),
('Motherly Moth Girl Keeps You Warm [F4F]','[F4M] / [F4F] / [F4TF] Motherly Moth Girl Keeps You Warm [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breastplay] [Outercourse] [Handjob/fingering] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [25min+] [Script: BowTieGuy_GWA]'),
('Motherly Moth Girl Keeps You Warm [F4TF]','[F4M] / [F4F] / [F4TF] Motherly Moth Girl Keeps You Warm [Gentle Fdom] [Size difference] [Thicc] [Monster Mommy] [Breastplay] [Outercourse] [Handjob/fingering] [Cozy blanket] [Kissing] [Thighjob] [Pinning you down] [Grinding] [Wrapped in wings] [Aftercare] [ASMR] [25min+] [Script: BowTieGuy_GWA]'),
('Lonely Kitty',NULL),
('F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help You Feel Better','[F4M] My Daughter is an Idiot for Breaking Up With You... Let Me Help You Feel Better [milf] [sex with your ex''s sweet + sexy mom] [realistic slow build] [kissing] [sloppy wet handjob + deep-throating blowjob] [dirty talk] [sucking my big tits] [riding you on the couch] [creampie] [improv]'),
('[f4m] Your Favourite Cousin',NULL);
CREATE INDEX alias_artist_id_idx ON Alias(artist_id);
CREATE INDEX audio_file_alias_id_idx ON AudioFile(alias_id);
CREATE INDEX audio_file_collection_id_idx ON AudioFile(collection_id);
CREATE TRIGGER AudioFile_ad AFTER DELETE ON AudioFile
        BEGIN
            INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, audio_title, collection_title)
            VALUES(
                'delete',
                old.id,
                old.title,
                (CASE
                 WHEN old.collection_id IS NULL THEN NULL
                 ELSE (SELECT title FROM FileCollection WHERE id = old.collection_id)
                 END)
            );
        END;
CREATE TRIGGER AudioFile_ai AFTER INSERT ON AudioFile
        BEGIN
            INSERT INTO Titles_fts_idx(rowid, audio_title, collection_title)
            VALUES (
                new.id,
                new.title,
                (CASE
                 WHEN new.collection_id IS NULL THEN NULL
                 ELSE (SELECT title FROM FileCollection WHERE id = new.collection_id)
                 END)
            );
        END;
CREATE TRIGGER AudioFile_au AFTER UPDATE ON AudioFile
        BEGIN
            -- delete old entry
            INSERT INTO Titles_fts_idx(Titles_fts_idx, rowid, audio_title, collection_title)
            VALUES(
                'delete',
                old.id,
                old.title,
                (CASE
                 WHEN old.collection_id IS NULL THEN NULL
                 ELSE (SELECT title FROM FileCollection WHERE id = old.collection_id)
                 END)
            );
            -- insert new one
            INSERT INTO Titles_fts_idx(rowid, audio_title, collection_title)
            VALUES (
                new.id,
                new.title,
                (CASE
                 WHEN new.collection_id IS NULL THEN NULL
                 ELSE (SELECT title FROM FileCollection WHERE id = new.collection_id)
                 END)
            );
        END;
COMMIT;
PRAGMA foreign_keys=on;