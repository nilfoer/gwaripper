import sys
import os
import glob
import shutil

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
if len(sys.argv) < 2:
    print("Usage: build_dir_dist output_dir")
    sys.exit(1)

out_dir = os.path.abspath(sys.argv[1])

if os.path.exists(out_dir):
    print("Output directory '", out_dir, "' will be deleted!")
    ans = input("Proceed(y/n)?")
    if ans.lower() not in ('y', 'yes'):
        print("Stopping!")
        sys.exit(1)
    else:
        shutil.rmtree(out_dir)
        os.makedirs(out_dir)
else:
    os.makedirs(out_dir)

found_files_rel = [fn for patt in globs
                   for fn in glob.glob(patt, recursive=True)]
found_files_rel.extend(files_to_include_in_root)
found_files_rel = set(found_files_rel)  # no duplicates
# but since we need a sorted list for our makedirs logic
found_files_rel = sorted(found_files_rel)

out_src_dir = out_dir
for fn in found_files_rel:
    fn = os.path.normpath(fn)
    # fn is relative!!
    out_file = os.path.join(out_dir, fn)
    out_src_dir_new = os.path.dirname(out_file)
    if not out_src_dir.startswith(out_src_dir_new):
        os.makedirs(out_src_dir_new)
        out_src_dir = out_src_dir_new

    shutil.copy2(fn, out_file, follow_symlinks=True)
    print("Copied:", out_file)
