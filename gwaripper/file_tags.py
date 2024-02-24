from datetime import datetime

import music_tag

from gwaripper.info import FileInfo, FileCollection, RedditInfo, children_iter_dfs

from typing import Optional, Any, Tuple, cast


def append_or_overwrite(music_tag_file: music_tag.file.AudioFile, key: str, value: Any):
    try:
        music_tag_file.append_tag(key, value)
    except music_tag.file.NotAppendable:
        music_tag_file[key] = value


def determine_audio_index_and_total(info: FileInfo, collection: FileCollection) -> Tuple[int, int]:
    num_audios = 0
    idx = -1
    for _, child in children_iter_dfs(collection.children, file_info_only=True):
        cast(FileInfo, child)
        if child.is_audio:
            num_audios += 1
        if info is child:
            idx = num_audios

    return idx, num_audios


def update_meta_tags(filename: str, info: FileInfo,
                     collection: Optional[FileCollection]):
    f = music_tag.load_file(filename)

    # append tags, so we don't overwrite pre-existing ones
    append_or_overwrite(f, 'title', info.title)
    append_or_overwrite(f, 'artist', info.author)

    if collection:
        append_or_overwrite(f, 'album', collection.title)
        append_or_overwrite(f, 'albumartist', collection.author)
        idx, num_audios_total = determine_audio_index_and_total(
            info, collection)
        append_or_overwrite(f, 'tracknumber', idx)
        append_or_overwrite(f, 'totaltracks', num_audios_total)

        if isinstance(collection, RedditInfo):
            append_or_overwrite(f, 'year', datetime.utcfromtimestamp(
                collection.created_utc).year)

    f.save()
