# Installation notes

1. Download and install a git client
2. Download and install Python 3 (including adding python to the system path)
3. Add the Dropbox API by running "pip install dropbox" from a command prompt
4. In C:\Users\MediaDesk\Documents, clone the git repository
5. Copy config_template.py to config.py, and edit as required (see below for note re Dropbox access token)
6. Create a folder %LOCALAPPDATA%\EasyWorshipSongHistory, and copy prefixes_to_ignore.txt to it
7. Run UploadSongHistoryIfSunday.bat as a logoff script (gpedit.msc, Computer Configuration > Windows Settings > Scripts (Startup/Shutdown))

# Dropbox

The song history file is uploaded to Dropbox. To generate an access token for the worship group Dropbox account:

1. Go to dropbox.com and sign in as worship@cca.uk.net
2. Click on ... at the far bottom-right, and select Developers
3. Click on App Console at the far top-right, and underneath My Apps click on the only app (EasyWorship Song History)
4. Underneath "Generated access token", click Generate
5. Copy the access token into config.py (see above)
