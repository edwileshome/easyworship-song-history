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
# If a song is projected multiple times during a service, only its first projection is written out.
#
# Command line options are provided by entering the following: python main.py -h

# Imports
import argparse
import config
import contextlib
import csv
import datetime
import dropbox
import dropbox.files
import logging
import re
import sqlite3

logging.basicConfig(filename=config.log_path, format='%(asctime)s [%(levelname)s] %(message)s', level=logging.INFO)

# Returns: datetime projected as YYYY-MM-DD hh:mm:ss, datetime projected as number of seconds since the epoch (1 Jan 1970),
#          title, author
# The datetime stored by EasyWorship seems odd - it is the number of 100s of nanoseconds since 21 December 1600. So we divide
# by 10000000 to get the number of seconds, then subtract a hardcoded number of seconds between 21 Dec 1600 and 1 Jan 1970.
# Action type 2 is "project" (not sure what the other action types are).
# We used to return song ID, but realised it does not uniquely identify a song (maybe it keeps an edit history).
sql = 'select datetime(datetime_since_epoch, "unixepoch"), datetime_since_epoch, title, author from \
          (select a.date/10000000-11644473600 datetime_since_epoch, s.title, s.author \
           from action a \
           join song s \
           on a.song_id = s.rowid \
           where action_type = 2)'

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

# SQLite collation function for case-insensitive sorting
def collate_utf8_u_ci(string1, string2):
    return cmp(string1.lower(), string2.lower())

# Read song history from databases specified in configuration file
def read_songhistory_dbs():
    rows = []
    for path in config.songhistory_db_paths:
        with sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES) as conn:
            conn.create_collation("UTF8_U_CI", collate_utf8_u_ci)
            with contextlib.closing(conn.cursor()) as cur:
                cur.execute(sql)
                for row in cur:
                    dt = to_datetime(row[0], row[1])
                    rows.append((dt,) + row[2:])

    # Order by date descending then time ascending, i.e. most recent service first but songs in each service appear in order
    rows.sort(key=lambda row: row[0].time())
    rows.sort(key=lambda row: row[0].date(), reverse=True)
    return rows

#----------------------------------------------------------------------------------------------------------------------#

def main():
    try:
        # Parse command-line arguments
        parser = argparse.ArgumentParser(description = "Converts the EasyWorship song history into a file, then uploads it.")
        parser.add_argument("-a, --all-songs", dest="ignore_prefixes", action="store_false", help="include all songs (do not ignore song prefixes)")
        parser.add_argument("-n, --no-upload", dest="upload", action="store_false", help="do not upload the converted file to the web")
        parser.set_defaults(ignore_prefixes=True)
        parser.set_defaults(upload=True)
        args = parser.parse_args()
        ignore_prefixes = args.ignore_prefixes
        upload_output_file = args.upload

        logging.info("Reading and converting song history")

        # Read song history from database(s)
        rows = read_songhistory_dbs()

        # Open list of song title prefixes to ignore
        if ignore_prefixes:
            with open(config.song_prefixes_path, "r") as prefixesfile:
                prefixes_to_ignore = prefixesfile.read().splitlines()

        # Open database and output file
        with open(config.songhistory_csv_path, "w") as csvfile:
            csvwriter = csv.writer(csvfile, lineterminator="\n")
            csvwriter.writerow(["Date", "Service", "Time Projected", "Title", "Author"])

            # Iterate through each query row
            previous_date = ""
            previous_service = ""
            songs_for_this_service = set()
            song_count = 0
            for row in rows:
                dt = row[0]
                service = to_service(dt)
                # Only continue if this row is part of a Sunday service
                if service is not None:
                    # Extract the remaining fields from the query row
                    date = to_date(dt)
                    time = to_time(dt)
                    title = remove_special_characters(row[1])
                    author = remove_special_characters(row[2])

                    # Ignore the title if it has no author and is in the list of prefixes to ignore
                    # e.g. It may be a Bible reading or some liturgy rather than a song
                    if ignore_prefixes:
                        ignore_title = (author == "") and is_in_prefixes_to_ignore(prefixes_to_ignore, title)
                    else:
                        ignore_title = False

                    if not ignore_title:
                        # Ignore the song if it has already been sung at this service
                        # Title + author is used to uniquely identify a song (because song ID in the database does not)
                        if previous_date != date or previous_service != service:
                            songs_for_this_service = set()
                        already_sung_at_this_service = (title + author) in songs_for_this_service
                        songs_for_this_service.add(title + author)
                        previous_date = date
                        previous_service = service

                        if not already_sung_at_this_service:
                            # Write out the song
                            song_count += 1
                            csvwriter.writerow([date, service, time, title, author])

        # Upload the output file to the web
        if upload_output_file:
            logging.info("Uploading converted song history (" + str(song_count) + " songs)")
            with open(config.songhistory_csv_path, "rb") as csvfile:
                file_to_upload = csvfile.read()

            dbx = dropbox.Dropbox(config.dropbox_access_token)
            dbx.files_upload(file_to_upload, config.songhistory_dropbox_csv_path, mode=dropbox.files.WriteMode.overwrite)

            logging.info("Song history uploaded")
        else:
            logging.info("Converted song history (" + str(song_count) + " songs)")
    except Exception as e:
        logging.exception(e)

if __name__ == '__main__':
    main()
