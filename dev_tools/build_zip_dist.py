import sys
import os
import glob
import zipfile

files_to_include_in_root = ['gwaripper-runner.py', 'LICENSE.txt', 'README.md', 'requirements.txt',
                            'setup.cfg', 'setup.py']

# If recursive is true, the pattern '**' will match any files and zero or more
# directories, subdirectories and symbolic links to directories. If the pattern
# is followed by an os.sep or os.altsep then files will not match.
# NOTE: When recursive is set, ** followed by a path separator matches 0 or more subdirectories.
# so gwaripper/**.py only finds gwaripper/*.py while gwaripper/**/*.py finds both
# gwaripper/*.py and gwaripper/extractors/*.py
# NOTE: just foo/** also matches directory foo/bar/
# foo/**/* also matches foo/bar/baz/ and not just files
# files starting with . won't be matched by default
globs = ['gwaripper/**/*.py', 'gwaripper_webGUI/static/**/*.*',
         'gwaripper_webGUI/templates/**/*.*',
         'gwaripper_webGUI/*.py']

# relpaths so we can replicate them more easily
if len(sys.argv) < 3:
    print("Usage: build_dir_dist project_root output_file")
    sys.exit(1)

root_dir = os.path.abspath(sys.argv[1])
out_zip_file = os.path.abspath(sys.argv[2])
out_dir = os.path.dirname(out_zip_file)
# so we get same directroy tree in archive
os.chdir(root_dir)

if os.path.exists(out_zip_file):
    print("Output file '", out_zip_file, "' will be deleted!")
    ans = input("Proceed(y/n)?")
    if ans.lower() not in ('y', 'yes'):
        print("Stopping!")
        sys.exit(1)
    else:
        os.remove(out_zip_file)
else:
    os.makedirs(out_dir, exist_ok=True)

found_files_rel = [fn for patt in globs
                   for fn in glob.glob(patt, recursive=True)]
found_files_rel.extend(files_to_include_in_root)
found_files_rel = set(found_files_rel)  # no duplicates
# but since we need a sorted list for our makedirs logic
found_files_rel = sorted(found_files_rel)

# You must call close() before exiting your program or essential records will not be written
# context manager handles that even on exceptions
# compression: ZIP_STORED (default), ZIP_DEFLATED, ZIP_BZIP2 or ZIP_LZMA
# modules might not be available which will result in RuntimeError
# compresslevel kwarg added in py3.7
# zlib -1 is default for compromise between speed and size equivalent to 6
# compresslevel=6
with zipfile.ZipFile(out_zip_file, 'x', compression=zipfile.ZIP_DEFLATED) as myzip:
    out_src_dir = out_dir
    for fn in found_files_rel:
        # fn is relative!!
        fn = os.path.normpath(fn)

        #  ZipFile.write(filename, arcname=None, compress_type=None, compresslevel=None)
        # Write the file named filename to the archive, giving it the archive
        # name arcname (by default, this will be the same as filename, but
        # without a drive letter and with leading path separators removed)
        # relative paths given will have the same path in the archive even paths including ..
        # abspaths have the drive letter removed
        myzip.write(fn)
        print("Added:", fn)
