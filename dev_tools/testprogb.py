import time, sys
import urllib.request

# http://stackoverflow.com/questions/3160699/python-progress-bar
# by Brian Khuu
# update_progress() : Displays or updates a console progress bar
## Accepts a float between 0 and 1. Any int will be converted to a float.
## A value under 0 represents a 'halt'.
## A value at 1 or bigger represents 100%
def update_progress(progress):
    barLength = 15 # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    block = int(round(barLength*progress))
    text = "\rPercent: [{0}] {1:.1f}% {2}".format( "#"*block + "-"*(barLength-block), progress*100, status)
    sys.stdout.write(text)
    sys.stdout.flush()


def update_progress_dl(blocknum, blocksize, totalsize):
    barLength = 15 # Modify this to change the length of the progress bar
    progress = blocknum * blocksize / totalsize
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    # nr of blocks
    block = int(round(barLength*progress))
    text = "\rPercent: [{0}] {1:.1f}% {2}".format( "#"*block + "-"*(barLength-block), progress*100, status)
    sys.stdout.write(text)
    sys.stdout.flush()
	
	
# http://stackoverflow.com/questions/13881092/download-progressbar-for-python-3
# by J.F. Sebastian
# combined with:
# http://stackoverflow.com/questions/3160699/python-progress-bar
# by Brian Khuu
def reporthook(blocknum, blocksize, totalsize):
    bar_len = 25 # Modify this to change the length of the progress bar
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize  # 1e2 == 100.0
        # nr of blocks
        block = int(round(bar_len*readsofar/totalsize))
        # %5.1f: pad to 5 chars and display one decimal, type float, %% -> escaped %sign
        # %*d -> Parametrized, width -> len(str(totalsize)), value -> readsofar
        # s = "\rDownloading: %5.1f%% %*d / %d" % (percent, len(str(totalsize)), readsofar, totalsize)
        sn = "\rDownloading: {:4.1f}% [{}] {:4.2f} / {:.2f} MB".format(percent, "#"*block + "-"*(bar_len-block) ,readsofar / 1024**2, totalsize / 1024**2)
        sys.stdout.write(sn)
        if readsofar >= totalsize: # near the end
            sys.stdout.write("\n")
    else: # total size is unknown
        sys.stdout.write("\rDownloading: %.2f MB" % (readsofar / 1024**2,))

# print("20:04:02 - INFO - Downloading: [F4M] Slippery Redux-script by Lurkinfortrouble with sexy sounds by GWAsub [HFO][Hypno][Listen to me stroke yo_002.m4a, File 1 of 1")
urllib.request.urlretrieve( "https://soundgasm.net/sounds/e764a6235fa9ca5e23ee10b3989721d97fc7242d.m4a",
							'test', reporthook)


# update_progress test script
# for i in range(100):
    # time.sleep(0.1)
    # update_progress(i/100.0)