# Runs the song history uploader (main.py) if executed on Sunday from 7pm

import main
from datetime import datetime

# If Sunday from 7pm, run the song history uploader
now = datetime.now()
if now.isoweekday() == 7 and now.hour >= 19:
    main.main()
