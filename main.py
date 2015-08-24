# Converts the EasyWorship song history into a file, then uploads it.
#
# The resulting file has these columns:
#   Date (most recent first)
#   Service (9:30am, 11:15am, 6:30pm)
#   Time Projected
#   Title
#   Author
#
# It includes only songs projected on a Sunday inside the assumed service projection times. These times are
# 9:28-11:00 (9:30am service), 11:13-13:00 (11:15am service), 18:28-21:00 (6:30pm service).
#
# It ignores song titles with certain prefixes (defined in a file), e.g. Bible readings or liturgy.

# Imports
import sqlite3
import config
import csv
import datetime
import urllib.request
import logging
import re

logging.basicConfig(filename=config.log_path, format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)

# Returns: datetime projected as YYYY-MM-DD hh:mm:ss, datetime projected as number of seconds since the epoch (1 Jan 1970),
#          song ID, title, author
# Ordered by date descending then time ascending, i.e. most recent service first but songs in each service appear in order
# The datetime stored by EasyWorship seems odd - it is the number of 100s of nanoseconds since 21 December 1600. So we divide
# by 10000000 to get the number of seconds, then subtract a hardcoded number of seconds between 21 Dec 1600 and 1 Jan 1970.
# Action type 2 is "project" (not sure what the other action types are).
sql = 'select datetime(datetime_since_epoch, "unixepoch"), datetime_since_epoch, song_id, title, author from \
          (select a.date/10000000-11644473600 datetime_since_epoch, s.rowid song_id, s.title, s.author \
           from action a \
           join song s \
           on a.song_id = s.rowid \
           where action_type = 2) \
       order by date(datetime_since_epoch, "unixepoch") desc, time(datetime_since_epoch, "unixepoch")'

# Convert to a datetime. There seems to have been a data import bug, as the EasyWorship 2007 data has the wrong number of seconds
# since epoch for times occurring during +0100 GMT. For that data we rely on the datetime string provided by SQLite as it ignores
# timezone. For new data (since 1 March 2015) we rely on the time since epoch.
def to_datetime(datetime_string, datetime_since_epoch):
    if datetime_since_epoch >= 1425168000: # 1 March 2015 at midnight
        return datetime.datetime.fromtimestamp(datetime_since_epoch)
    else:
        return datetime.datetime.strptime(datetime_string, "%Y-%m-%d %H:%M:%S")

# Find the Sunday service referred to by a datetime (if any)
def to_service(dt):
    # If datetime is a Sunday
    if dt.weekday() == 6:
        timeinmins = dt.hour * 60 + dt.minute
        # Assign a service based on time: 09:28-11:00, 11:13-13:00, 18:28-21:00
        if timeinmins >= 9*60+28 and timeinmins <= 11*60:
            return "9:30am"
        if timeinmins >= 11*60+13 and timeinmins <= 13*60:
            return "11:15am"
        if timeinmins >= 18*60+28 and timeinmins <= 21*60:  
            return "6:30pm"
    return None
    
# Extract the date from a datetime
def to_date(dt):
    return dt.strftime("%d/%m/%Y")

# Extract the time from a datetime
def to_time(dt):
    return dt.strftime("%H:%M:%S")

# Return true if the title is prefixed by any of the supplied prefixes, otherwise false
def is_in_prefixes_to_ignore(prefixes, title):
    return any(title.lower().startswith(prefix.lower()) for prefix in prefixes)

# Remove special characters from the specified string
def remove_special_characters(str):
    return re.sub('[^a-zA-Z0-9 ‘’\!\&\(\)\-\.\;\:\,\?\/\']', '', str)
    
#----------------------------------------------------------------------------------------------------------------------#

def main():
    try:
        logging.info("Reading and converting song history")

        # Open list of song title prefixes to ignore
        with open(config.song_prefixes_path, "r") as prefixesfile:
            prefixes_to_ignore = prefixesfile.read().splitlines()
            
        # Open database and output file
        with open(config.songhistory_csv_path, "w") as csvfile:
            csvwriter = csv.writer(csvfile, lineterminator="\n")
            csvwriter.writerow(["Date", "Service", "Time Projected", "Title", "Author"])

            # Open connection to database, open a cursor and execute query
            conn = sqlite3.connect(config.songhistory_db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            cur = conn.cursor()
            cur.execute(sql)

            # Retrieve each query row
            previous_date = ""
            previous_service = ""
            song_ids_for_current_date = set()
            song_count = 0
            for row in cur:
                dt = to_datetime(row[0], row[1])
                service = to_service(dt)
                # Only continue if this row is part of a Sunday service
                if service is not None:
                    # Extract the remaining fields from the query row
                    date = to_date(dt)
                    time = to_time(dt)
                    song_id = row[2]
                    title = remove_special_characters(row[3])
                    author = remove_special_characters(row[4])
                    
                    # Ignore the title if it has no author and is in the list of prefixes to ignore
                    # e.g. It may be a Bible reading or some liturgy rather than a song
                    ignore_title = (author == "") and is_in_prefixes_to_ignore(prefixes_to_ignore, title)

                    if not ignore_title:
                        # Ignore the song if it has already been sung at this service
                        if previous_date != date or previous_service != service:
                            song_ids_for_this_service = set()
                        already_sung_at_this_service = song_id in song_ids_for_this_service
                        song_ids_for_this_service.add(song_id)
                        previous_date = date
                        previous_service = service

                        if not already_sung_at_this_service:
                            # Write out the song
                            song_count += 1
                            csvwriter.writerow([date, service, time, title, author])

            # Close the cursor and connection
            cur.close()
            conn.close()

        logging.info("Uploading converted song history (" + str(song_count) + " songs)")
            
        # Upload the output file to the web
        with open(config.songhistory_csv_path, "rb") as csvfile:
            file_to_upload = csvfile.read()

        request = urllib.request.Request(url=config.upload_url, data=file_to_upload, method="PUT")
        response = urllib.request.urlopen(request)
        
        logging.info("Song history uploaded")
    except Exception as e:
        logging.exception(e)

if __name__ == '__main__':
    main()
