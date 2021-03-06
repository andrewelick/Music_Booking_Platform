from venueimports import datetime
from venueimports import string
from venueimports import random
from venueimports import time
from venueimports import pymysql
from venueimports import requests
from venueimports import smtplib
from venueimports import MIMEMultipart
from venueimports import MIMEText
from venueimports import Template
from venueimports import stripe
import os
import shutil
import urllib.parse
import json
import base64
import re
import traceback
import bcrypt
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from requests.auth import HTTPBasicAuth
import boto3
from botocore.client import Config
from dotenv import load_dotenv


#Load env variables
load_dotenv('test.env')

#Connect to database
def connect_to_database():
    try:
        conn = pymysql.connect(
            host= os.getenv('DATABASE_LOCATION'),
            db= os.getenv('DATABASE_NAME'),
            user= os.getenv('DATABASE_USERNAME'),
            password= os.getenv('DATABASE_PASSWORD'),
        )
        return conn
    except Exception as e:
        print (e)
        print ("Could not connect database")
        conn = False
        return conn

def check_email_used(email):
    #Connect to database
    conn = connect_to_database()

    if conn is not False:
        c = conn.cursor()

        result = c.execute("""SELECT email FROM accounts WHERE email=%s""", (email,))

        if result != 0:
            return json.dumps({"result":"email used"})
        else:
            return json.dumps({"result": "email open"})

def create_default_aws_picture(uid):
    picture_url = "static/user_pictures/profile_pictures/"+uid+"_profile.jpg"
    data = open('static/default_profile.jpg', 'rb')

    #AWS client setup
    s3 = boto3.resource(
        's3',
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.getenv('AWS_ACCESS_SECRET_KEY'),
        config = Config(signature_version = 's3v4')
    )
    #Write file to AWS S3 bucket
    s3.Bucket(os.getenv('AWS_BUCKET_NAME')).put_object(Key = picture_url, Body = data, ContentType = 'image/jpeg')

    return True

#Send picture to AWS bucket
def send_profile_picture_to_aws(uid):
    picture_url = "static/user_pictures/profile_pictures/"+uid+"_profile.jpg"
    data = open(picture_url, 'rb')

    #AWS client setup
    s3 = boto3.resource(
        's3',
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.getenv('AWS_ACCESS_SECRET_KEY'),
        config = Config(signature_version = 's3v4')
    )
    #Write file to AWS S3 bucket
    s3.Bucket(os.getenv('AWS_BUCKET_NAME')).put_object(Key = picture_url, Body = data, ContentType = 'image/jpeg')

    return True

#Get picture from AWS bucket bluffbucket
def get_profile_picture_url(uid, ajax_request = None):

    #AWS client setup
    s3 = boto3.client(
        's3',
        region_name = 'us-east-2',
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.getenv('AWS_ACCESS_SECRET_KEY'),
        config = Config(signature_version = 's3v4')
    )

    picture_url = "static/user_pictures/profile_pictures/"+uid+"_profile.jpg"

    #Send request for picture
    result = s3.generate_presigned_url(
                    'get_object',
                    Params = {
                        'Bucket': os.getenv('AWS_BUCKET_NAME'),
                        'Key': picture_url,
                    },
                    ExpiresIn = 3600,
                    )

    if ajax_request == "yes":
        return json.dumps({'success': result})
    else:
        return result

#Create account
def create_new_account(email,password,confirm_password,name,account_type):

    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()

        try:
            #Check if any field is empty
            if email == "" or password == "" or confirm_password == "" or name == "" or account_type == "0":
                error = True
            else:
                #Check if password is 8 or more characters
                if len(password) < 8:
                    error = True
                else:
                    #Check if passwords match
                    if password != confirm_password:
                        error = True
                    else:
                        error = False

            #if error quit, else continue
            if error is True:
                return json.dumps({'error': 'Invalid form fields'})
            else:
                #Used for account creation
                uid = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)]) #Combine letters and numbers, in a 12 digit string
                #Hash the password
                password = bytes(password, encoding="ascii")
                hashed_password = bcrypt.hashpw(password, bcrypt.gensalt(10))
                date_joined = datetime.date.today() #Get the current date

                new_account_details = (uid,email,hashed_password,name,account_type,date_joined)
                #Check if email is already being used
                used_email = c.execute("""SELECT email FROM accounts WHERE email=%s""", (email,))

                if used_email == 0:

                    #Create account row
                    c.execute("""INSERT INTO accounts (uid,email,password,name,account_type,date_joined) VALUES(%s,%s,%s,%s,%s,%s)""", new_account_details)

                    #Create payments_account row
                    c.execute("""INSERT INTO payment_accounts (uid) VALUES(%s)""", (uid,))

                    #Account type Venue
                    if account_type == '1':
                        #Create venue_profile_details
                        c.execute("""INSERT INTO venue_profile_details (uid) VALUES(%s)""", (uid,))
                        #Create venue links row
                        c.execute("""INSERT INTO venue_account_links (uid) VALUES (%s)""", (uid,))

                    #Account type Artist
                    if account_type == '2':
                        #Create artist_profile_details row
                        c.execute("""INSERT INTO artist_profile_details (uid) VALUES(%s)""", (uid,))
                        #Create artist_account_links row
                        c.execute("""INSERT INTO artist_account_links (uid) VALUES(%s)""", (uid,))
                        #Create connected_app_tokens row
                        c.execute("""INSERT INTO spotify_access_tokens (uid) VALUES(%s)""", (uid,))

                    conn.commit()

                    #Send picture to AWS bucket bluffbucket
                    create_default_aws_picture(uid)


                    return json.dumps({'success': 'Account created'})
                else:
                    return json.dumps({'error': 'Email already used with another account'})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'error when creating account'})
        finally:
            if conn:
                conn.close()

#Login to account
def login_account(email,password):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Find account
            found_account = c.execute("""SELECT password FROM accounts WHERE email=%s""", (email,))

            #If email address has matching account
            if found_account == 1:
                saved_password = c.fetchone()[0]
                saved_password = bytes(saved_password, encoding=("ascii"))

                #Encode password
                password = bytes(password, encoding="ascii")

                #Check if password matches saved one
                if bcrypt.checkpw(password, saved_password):
                    return True
                else:
                    return False

            else:
                return False
        except Exception as e:
            print (e)
        finally:
            if conn:
                conn.close()

#Reset password and send email
def send_reset_password(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()

        try:
            find_account = c.execute("""SELECT uid, name FROM accounts WHERE email=%s""", (email,))

            if find_account == 1:
                #User details
                user_details = c.fetchone()
                uid = user_details[0]
                username = user_details[1]

                #Combine letters and numbers, in a 12 digit string
                reset_code = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(10)])
                find_reset_password = c.execute("""SELECT * FROM password_resets WHERE uid=%s""",(uid,))

                #If reset code already exists
                if find_reset_password == 1:
                    c.execute("""UPDATE password_resets SET reset_code=%s WHERE uid=%s""", (reset_code,uid,))
                else:
                    c.execute("""INSERT INTO password_resets (uid,reset_code) VALUES (%s, %s)""", (uid,reset_code,))
                conn.commit()

                #Reset link that is sent to the user
                reset_link = "http://localhost:8000/changepassword?uid="+uid+"&reset_code="+reset_code

                #Get the reset email file
                with open(r'Templates/email_files/resetpassword.html', 'r', encoding='utf-8') as email_template_file:
                    template_content = Template(email_template_file.read())
                    email_template_file.close()

                #Set up SMTP server, SSL connection
                #ssl_context = pyOpenSSL.SSLv3_METHOD(SSLv3_METHOD)
                smtp_server = smtplib.SMTP_SSL('smtp.gmail.com',465)
                smtp_server.login('andrew@blufftour.com', 'fzzicdixhkflkhok')

                #Creates the message
                msg = MIMEMultipart()

                #Change emailauth.txt variables
                message = template_content.substitute(RESET_LINK=reset_link, USERNAME=username)

                #Set up email parameters
                msg['From']= 'Bluff Tour'
                msg['To']= email
                msg['subject']='Bluff Tour password reset request'
                msg.attach(MIMEText(message, 'html')) #Add emailauth.txt to email

                #Send the message
                smtp_server.send_message(msg)

                #Close SMTP connection
                smtp_server.quit()

                return json.dumps({'success': 'email sent'})
            else:
                return json.dumps({'error': 'no account'})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'error sending email'})
        finally:
            if conn:
                conn.close()

#Change password
def change_password(uid,reset_code,password):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            find_reset_code = c.execute("""SELECT * FROM password_resets WHERE uid=%s and reset_code=%s""", (uid,reset_code))

            if find_reset_code == 1:
                hashed_password = hashlib.sha256(password.encode()).hexdigest() #Hash the password

                c.execute("""UPDATE accounts SET password=%s WHERE uid=%s""", (hashed_password,uid,))
                c.execute("""DELETE FROM password_resets WHERE uid=%s""", (uid,))
                conn.commit()
                return True
            else:
                return False
        except Exception as e:
            print (e)
        finally:
            if conn:
                conn.close()

#Get uid of user
def get_uid(email):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT uid FROM accounts WHERE email=%s""", (email,))
            uid = c.fetchone()[0]
            return uid
        except Exception as e:
            return False
        finally:
            if conn:
                conn.close()

#Get email of user
def get_email(uid):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT email FROM accounts WHERE uid=%s""", (uid,))
            email = c.fetchone()[0]
            return email
        except:
            return False
        finally:
            if conn:
                conn.close()

#Profile artist setup
def artist_profile_setup(email,genre,member,bio):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            uid = c.execute("""SELECT uid FROM accounts WHERE email=%s""", (email,))

            if uid != 0:
                uid = c.fetchone()[0]
                find_account = c.execute("""SELECT * FROM artist_profile_details WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
                #Check if row is made
                if find_account == 1:
                    c.execute("""UPDATE artist_profile_details SET genre=%s, member=%s, bio=%s WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (genre,member,bio,email,))
                else:
                    c.execute("""INSERT INTO artist_profile_details (uid,genre,member,bio) VALUES(%s,%s,%s,%s)""", (uid,genre,member,bio,))
                conn.commit()

                return json.dumps({'success': 'Updated profile'})
            else:
                return False
        except Exception as e:
            print (e)
            return json.dumps({'error': 'We were update your profile at this time'})
        finally:
            if conn:
                conn.close()

#Profile venue setup
def venue_profile_setup(email,business_name,business_type,location,bio):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""UPDATE venue_profile_details SET business_name=%s, type=%s, location=%s, bio=%s WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (business_name,business_type,location,bio,email,))
            conn.commit()

            #Get uid for profile picture
            c.execute("""SELECT uid FROM accounts WHERE email=%s""", (email,))
            uid = c.fetchone()[0]

            return json.dumps({'success': 'Your profile has been updated'})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'Error updating profile'})
        finally:
            if conn:
                conn.close()

#Save artist profile links
def save_artist_profile_links(email,spotify_link,bandcamp_link,twitter_link,instagram_link,facebook_link):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""UPDATE artist_account_links SET spotify_link=%s, bandcamp_link=%s, twitter_link=%s, instagram_link=%s, facebook_link=%s WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (spotify_link,bandcamp_link,twitter_link,instagram_link,facebook_link,email,))
            conn.commit()

            return json.dumps({'success': 'Successfully updated profile links'})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'Unable to update profile links'})
        finally:
            if conn:
                conn.close()

#Save venue profile links
def save_venue_profile_links(email,twitter,instagram,facebook,personal_website):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""UPDATE venue_account_links SET twitter=%s, instagram=%s, facebook=%s, personal_website=%s WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (twitter,instagram,facebook,personal_website,email,))
            conn.commit()

            return json.dumps({'success': 'Successfully saved links'})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'Error updating links'})
        finally:
            if conn:
                conn.close()

#Check account type
def check_account_type(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT account_type FROM accounts WHERE email=%s""", (email,))
            account_type = c.fetchone()[0]

            if account_type == 1:
                account_type = 'venue'
            elif account_type == 2:
                account_type = 'artist'

            return account_type
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get artist links
def get_artist_links(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT spotify_link, twitter_link, facebook_link FROM artist_account_links WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            artist_links = c.fetchone()

            #Used to move edited data into
            artist_links2 = []

            #Loop through each link and replace None with empty
            for x in artist_links:
                if x is None:
                    x = ""
                artist_links2.append(x)

            artist_links_dict = {
                'spotify': artist_links2[0],
                'twitter': artist_links2[1],
                'facebook': artist_links2[2],
            }

            #Format facebook link
            if (artist_links_dict['facebook'] != ""):
                artist_links_dict['facebook'] = artist_links_dict['facebook'].split("/")[-1]

            print (artist_links_dict)
            return artist_links_dict

        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get venue links
def get_venue_links(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT * FROM venue_account_links WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            venue_links = c.fetchone()
            return venue_links
        except Exception as e:
            return False
        finally:
            if conn:
                conn.close()

#Get artist profile information
def get_artist_profile_details(email):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT artist_profile_details.*,accounts.name FROM artist_profile_details, accounts WHERE artist_profile_details.uid IN (SELECT uid FROM accounts WHERE email=%s) AND accounts.email=%s""", (email,email,))
            artist_details = list(c.fetchone())

            return artist_details
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get venue profile information
def get_venue_profile_details(email):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT * FROM venue_profile_details WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            venue_details = list(c.fetchone())

            return venue_details
        except Exception as e:
            return False
        finally:
            if conn:
                conn.close()

#Save artist media
def create_artist_media(uid, type, src):
    #Connect to database
    conn = connect_to_database()

    if conn is not False:
        c = conn.cursor()

        try:
            #Insert into artist_media table
            c.execute("""INSERT INTO artist_media (uid, type, src) VALUES (%s, %s, %s)""", (uid, type, src,))
            conn.commit()

            return json.dumps({'success': 'saved'})
        except Exception as e:
            print (e)
            return json.dumps({'error': "Could not save media"})
        finally:
            if conn:
                conn.close()

#Get artist media for artistprofile
def get_artist_media(uid):
    #Connect to database
    conn = connect_to_database()

    if conn is not False:
        c = conn.cursor()

        try:
            #Insert into artist_media table
            c.execute("""SELECT media_id, src FROM artist_media WHERE uid = %s""", (uid,))
            all_media = c.fetchall()

            #Second list for results
            all_media2 = []

            #Loop through all items
            for x in all_media:
                dict = {
                    'media_id': x[0],
                    'src': x[1],
                }

                all_media2.append(dict)

            #Reverse list
            all_media2 = all_media2[::-1]

            return json.dumps({'success': all_media2})
        except Exception as e:
            print (e)
            return json.dumps({'error': "Could not load media"})
        finally:
            if conn:
                conn.close()

#Delete artist media for artistprofile
def delete_artist_media(uid, media_id):
    #Connect to database
    conn = connect_to_database()

    if conn is not False:
        c = conn.cursor()

        try:
            #Insert into artist_media table
            c.execute("""DELETE FROM artist_media WHERE uid = %s AND media_id = %s""", (uid, media_id,))
            conn.commit()

            return json.dumps({'success': "Deleted media"})
        except Exception as e:
            print (e)
            return json.dumps({'error': "Could not delete media"})
        finally:
            if conn:
                conn.close()

#Get featured venues
def get_showcase_venues():
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT uid,business_name,type,bio FROM venue_profile_details LIMIT 4""")
            venue_showcase = c.fetchall()

            showcase_list = []

            for venue in venue_showcase:

                venue_details = {
                    'busi_uid': venue[0],
                    'busi_name': venue[1],
                    'busi_type': venue[2],
                    'busi_bio': venue[3],
                }

                showcase_list.append(venue_details)

            return showcase_list
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get featured artists for showcase
def get_featured_artists(api = None, limit = None):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:

            if limit is None:
                limit = 10

            find_artists = c.execute("""SELECT accounts.uid, accounts.name, artist_profile_details.bio, artist_profile_details.genre FROM accounts, artist_profile_details WHERE account_type=2 AND artist_profile_details.uid = accounts.uid ORDER BY RAND() LIMIT %s""", (limit,))
            results = c.fetchall()

            all_artists_list = []

            for artist in results:
                artist_details = {
                    'uid': artist[0],
                    'artist_name': artist[1],
                    'bio': artist[2],
                    'genre': artist[3]
                }

                all_artists_list.append(artist_details)

            if api:
                return json.dumps({'success': all_artists_list})
            else:
                return all_artists_list
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#-#-#-# ARTIST BIDS SECTION #-#-#-#-#-#-# ------------------------------

#Check for winning bid
def check_winning_bid(show_id):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            winner_bid = c.execute("""SELECT uid FROM show_bids WHERE show_id = %s AND winner = 1""", (show_id,))

            #If there is a winner
            if winner_bid == 1:
                winner_info = {'artist_uid': c.fetchone()[0]}

                print (winner_info['artist_uid'])

                #Get winning bidder name & genre
                c.execute("""SELECT accounts.name,artist_profile_details.genre FROM accounts,artist_profile_details WHERE accounts.uid=%s AND artist_profile_details.uid=%s""", (winner_info['artist_uid'],winner_info['artist_uid']))
                name = c.fetchone()

                winner_info.update({
                    'artist_name': name[0],
                    'genre': name[1]
                })

                result = winner_info
            else:
                result = "No winner"

            return json.dumps({'success': result})

        except Exception as e:
            print (e)
            return json.dumps({'error': 'Could not check for show status'})
        finally:
            if conn:
                conn.close()

#Get bids for single listing page
def get_full_bid_info(show_id):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get all bids from show
            find_bids = c.execute("""SELECT show_bids.*, artist_profile_details.genre,  artist_profile_details.bio, accounts.name FROM show_bids, artist_profile_details, accounts WHERE show_id= %s AND  artist_profile_details.uid = show_bids.uid AND accounts.uid = show_bids.uid ORDER BY date DESC""", (show_id,))
            all_bids = c.fetchall()

            #Check if there no bids
            if (len(all_bids) == 0):
                result = "no bids"

            else:

                #Loop through each bid and format into dict
                bids_list = []

                for x in all_bids:
                    new_dict = {
                        'bid_details': {
                            'bid_id': x[0],
                            'show_id': x[1],
                            'amount': x[3],
                            'date_posted': x[4].strftime("%b %d"),
                            'winner': x[5],
                        },
                        'artist_details': {
                            'uid': x[2],
                            'name': x[8],
                            'genre': x[6],
                            'bio': x[7],
                        },
                    }

                    bids_list.append(new_dict)

                result = bids_list

            return json.dumps({'success': result})
        except Exception as e:
            print (e)
            return json.dumps({'error': str(e)})
        finally:
            if conn:
                conn.close()

#Find all bids placed
def get_all_artist_bids(uid):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Todays date
            today = datetime.datetime.now()

            #Get bids by artist that are active
            c.execute("""SELECT show_bids.show_id, show_bids.bid_amount, show_postings.uid, show_postings.show_date, show_postings.show_time, show_postings.location, venue_profile_details.business_name FROM show_bids, show_postings, venue_profile_details WHERE show_bids.uid = %s AND show_bids.winner = 0 AND show_postings.show_date > %s AND show_postings.show_id = show_bids.show_id AND venue_profile_details.uid = show_postings.uid AND show_postings.won = 0 """, (uid, today,))
            all_bids = c.fetchall()

            if len(all_bids) != 0:

                all_bids_list = []

                #loop through each result and format to dictionary
                for x in all_bids:
                    bid_dict = {
                        'show_id': x[0],
                        'business_uid': x[2],
                        'business_name': x[6],
                        'bid_price': x[1],
                        'show_date': x[3].strftime("%b %d"),
                        'show_time': x[4],
                        'show_location': x[5]
                    }

                    all_bids_list.append(bid_dict)
            else:
                all_bids_list = "no bids"

            return json.dumps({'success': all_bids_list})
        else:
            results = "could not connect to database"

        return json.dumps({'error': result})
    except Exception as e:
        print (e)
        return json.dumps({'error': str(e)})
    finally:
        if conn:
            conn.close()

#Get all upcoming winning shows for artist
def get_upcoming_artist_shows(uid):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            today_date = datetime.datetime.now()

            #Get shows that artist has won and have not happened yet
            c.execute("""SELECT show_postings.show_id, show_postings.uid, venue_profile_details.business_name, show_bids.bid_amount, show_postings.show_date, show_postings.show_time, show_postings.set_length, show_postings.location FROM show_bids, show_postings, venue_profile_details WHERE show_bids.show_id = show_postings.show_id AND show_bids.uid = %s AND show_postings.uid = venue_profile_details.uid AND show_bids.winner = 1 AND show_postings.show_date > %s""", (uid,today_date))
            upcoming_shows = c.fetchall()

            if len(upcoming_shows) != 0:

                upcoming_shows_list = []

                #Loop through each result and format to dict
                for x in upcoming_shows:
                    new_dict = {
                        'show_id': x[0],
                        'business_uid': x[1],
                        'business_name': x[2],
                        'bid_amount': x[3],
                        'show_date': str(x[4].strftime("%b %d")),
                        'show_time': x[5],
                        'set_length': x[6],
                        'show_location': x[7]
                    }

                    upcoming_shows_list.append(new_dict)

                result = upcoming_shows_list
            else:
                result = "no upcoming shows"

            return json.dumps({'success': result})
        else:
            return json.dumps({'error': 'Could not connect to database'})
    except Exception as e:
        print (e)
        return json.dumps({"result": str(e)})

#Make a bid on a show posting
def place_bid_on_show(uid,show_id,bid_amount):
    try:
        #Connect to database
        conn = connect_to_database()
        if conn is not False:
            c = conn.cursor()

            #Check if user has already placed bid
            already_bid = c.execute("""SELECT uid FROM show_bids WHERE show_id=%s AND uid=%s""", (show_id,uid,))
            if already_bid == 0:

                #Current date
                date = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                #Generate bid id
                bid_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
                #Check bid_id and get new one if already used
                bid_id_unique = c.execute("""SELECT bid_id FROM show_bids WHERE bid_id=%s""",(bid_id,))

                while bid_id_unique > 0:
                    bid_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
                    bid_id_unique = c.execute("""SELECT bid_id FROM show_bids WHERE bid_id=%s""",(bid_id))

                bid_details = (bid_id,show_id,uid,bid_amount,date)
                #Create new bid row
                c.execute("""INSERT INTO show_bids(bid_id,show_id,uid,bid_amount,date) VALUES(%s,%s,%s,%s,%s)""", (bid_details))
                conn.commit()

                #create_new_notification(send_id,rec_id,noti_type,show_id=show_id)

                return json.dumps({'success': 'Placed new bid'})
            else:
                #User already placed bid
                return json.dumps({'error': 'You have already placed a bid for this show'})
        else:
            return json.dumps({'error': 'Could not connect to database'})
    except Exception as e:
        print (e)
        return json.dumps({'error': str(e)})
    finally:
        if conn:
            conn.close()

#Delete bid from show
def delete_bid(bid_id,artist_uid):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Delete bid from database
            c.execute("""DELETE FROM show_bids WHERE bid_id = %s AND uid = %s""",(bid_id,artist_uid,))
            conn.commit()

            return json.dumps({'success': 'bid deleted'})
        except Exception as e:
            print (e)
            return json.dumps({'error': str(e)})
        finally:
            if conn:
                conn.close()

#Accept bid for a show positng
def accept_bid_offer(bid_id):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get show bid details
            find_bid = c.execute("""SELECT show_bids.bid_amount, show_bids.uid, show_postings.show_id, show_postings.uid, show_postings.show_date FROM show_bids, show_postings WHERE show_bids.bid_id = %s AND show_bids.show_id = show_postings.show_id""", (bid_id,))

            #If bid is found
            if find_bid == 1:
                bid_details = c.fetchone()

                show_price = int(bid_details[0]) * 100
                artist_uid = bid_details[1]
                show_id = bid_details[2]
                venue_uid = bid_details[3]
                show_date = bid_details[4]
                current_date = datetime.datetime.now()
                status = "waiting"

                #Details for saving transaction
                transaction_details = (
                    show_id,
                    venue_uid,
                    artist_uid,
                    show_price,
                    show_date,
                    current_date,
                    status
                )

                #Save transaction to payment_transactions
                c.execute("""INSERT INTO payment_transactions (show_id, venue_id, artist_id, show_price, show_date, transaction_date, status) VALUES (%s, %s, %s, %s, %s, %s, %s)""", (transaction_details))

                #Change show_bids winner to 1
                c.execute("""UPDATE show_bids SET winner=1 WHERE show_id=%s AND uid=%s""", (show_id,artist_uid,))

                #Change show postings won to 1
                c.execute("""UPDATE show_postings SET won = 1 WHERE show_id = %s""", (show_id))

                conn.commit()

                #Send notification
                create_new_notification(venue_uid,artist_uid,3,show_id=show_id)

                return json.dumps({'success': 'Bid has been accepted'})
            else:
                return json.dumps({'error': 'could not find show'})

        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

###---MESSAGES SECTION #######----------------------------------------------

#Calculate time sent ago
def cal_time_sent(time_sent):
    #Calculate time ago
    time_difference = datetime.datetime.utcnow() - time_sent
    day_diff = time_difference.days
    second_diff = time_difference.seconds

    #If post is less than a day old
    if day_diff == 0:
        #If time is less than a minute old
        if second_diff < 60:
            return "Just Now"
        elif second_diff < 3600:
            return str(second_diff // 60)+" mins ago"
        elif second_diff < 7200:
            return "an hour ago"
        elif second_diff < 86400:
            return str(second_diff // 3600)+" hours ago"
    #If a day has passed
    elif day_diff == 1:
        return "Yesterday"
    #one week
    elif day_diff < 7:
        return str(day_diff) + " days ago"
    else:
        return time_sent.strftime("%x")


#Create new message
def create_new_message(email,rec_id,message):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            send_id = get_uid(email)
            date_sent = datetime.datetime.utcnow()

            #Check if there has already been a thread made between the 2 users
            find_thread = c.execute("""SELECT * FROM messages WHERE (send_id IN (SELECT uid FROM accounts WHERE email=%s) AND rec_id=%s) OR (send_id=%s AND rec_id IN (SELECT uid FROM accounts WHERE email=%s))""", (email,rec_id,rec_id,email,))

            #If new create thread id
            if find_thread == 0:
                thread_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
            else:
                thread_id = c.fetchone()[0]

            message_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])

            #Check message id to make sure unique
            message_id_unique = c.execute("""SELECT message_id FROM messages WHERE message_id=%s""", (message_id,))

            #If message if is used try again
            while message_id_unique > 0:
                message_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
                message_id_unique = c.execute("""SELECT message_id FROM messages WHERE message_id=%s""", (message_id,))

            c.execute("""INSERT INTO messages(thread_id,message_id,send_id,rec_id,date_sent,message) VALUES (%s,%s,%s,%s,%s,%s)""", (thread_id,message_id,send_id,rec_id,date_sent,message,))
            conn.commit()
            return True
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Find messages threads
def get_messages_threads(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            uid = get_uid(email)
            c.execute("""SELECT thread_id FROM messages WHERE send_id=%s OR rec_id=%s""", (uid,uid,))
            all_threads_repeated = c.fetchall()

            #Filter down messages to threads
            all_threads = set()
            for thread in all_threads_repeated:
                all_threads.add(thread)

            #Get all thread details
            all_threads_details = []
            for thread in all_threads:
                c.execute("""SELECT * FROM messages WHERE thread_id=%s ORDER BY date_sent DESC LIMIT 1""", (thread,))
                thread_details = list(c.fetchone())

                #Get name of account
                if thread_details[2] == uid:
                    c.execute("""SELECT name FROM accounts WHERE uid=%s""", (thread_details[3],))

                else:
                    c.execute("""SELECT name FROM accounts WHERE uid=%s""", (thread_details[2],))

                #Add name
                name = c.fetchone()[0]
                thread_details.append(name)

                #Calcuate the time message was sent
                time_from = cal_time_sent(thread_details[4])
                thread_details.append(time_from)

                #Check if notifications from new messages
                notification_number = c.execute("""SELECT * FROM notifications WHERE send_id=%s AND rec_id=%s AND type=1""", (thread_details[2],uid,))
                thread_details.append(notification_number)

                #Add thread details to list
                all_threads_details.append(thread_details)

            def getTime(elem):
                return elem[4]

            return sorted(all_threads_details, key=getTime, reverse=True)
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get all messages in one thread conversation
def get_messages_one_thread(thread_id, **kwargs):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            count = c.execute("""SELECT * FROM messages WHERE thread_id=%s ORDER BY date_sent""", (thread_id,))

            #Check if pagination is activated
            if 'count' not in kwargs:
                #Let messages know there are more to be loaded
                if count > 10:
                    more_messages = 1
                else:
                    more_messages = 0

                count = 10
            else:
                #If max load is less more than amount of messages
                if count < kwargs['count']:
                    more_messages = 0
                else:
                    more_messages = 1

                count = kwargs['count']

            #Get messages within load limit
            c.execute("""SELECT * FROM messages WHERE thread_id=%s ORDER BY date_sent DESC LIMIT %s""", (thread_id, count,))

            all_messages = c.fetchall()

            #Loop through all messages and convert time
            all_messages_details = []
            for message in all_messages[::-1]:
                #Convert details to list
                message = list(message)

                #Get message sender name
                c.execute("""SELECT name FROM accounts WHERE uid=%s LIMIT 1""", (message[2],))
                send_name = c.fetchone()[0]
                message.append(send_name)

                #Calcuate time sent ago
                message[4] = cal_time_sent(message[4])

                #Add message details
                all_messages_details.append(message)

            return [all_messages_details, more_messages]
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get details of other user in thread
def get_thread_other_user(rec_id):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Check account type
            c.execute("SELECT account_type FROM accounts WHERE uid=%s", (rec_id,))
            account_type = c.fetchone()[0]

            if account_type == 2:
                c.execute("SELECT uid, name FROM accounts WHERE uid=%s", (rec_id,))
                user_details = c.fetchone()
            else:
                c.execute("SELECT uid, business_name FROM venue_profile_details WHERE uid=%s", (rec_id,))
                user_details = c.fetchone()

            return user_details
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#-#-#-# NOTIFICATIONS SECTION -#-#-#-#-#-#-#-#-#-#

#Create notification
def create_new_notification(send_id,rec_id,type,**kwargs):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:

            #Notification id
            noti_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])

            #Check if notification id is being used
            old_noti_id = c.execute("""SELECT * FROM notifications WHERE noti_id=%s""", (noti_id,))
            #Make new noti_if it is
            while old_noti_id > 0:
                noti_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
                old_noti_id = c.execute("""SELECT * FROM notifications WHERE noti_id=%s""", (noti_id,))

            time_sent = datetime.datetime.utcnow()

            #If notifcation is a bid
            if kwargs:
                show_id = kwargs['show_id']
            else:
                show_id = "NULL"

            c.execute("""INSERT INTO notifications(noti_id,rec_id,send_id,type,time_sent,user_read,show_id) VALUES(%s,%s,%s,%s,%s,%s,%s)""", (noti_id,rec_id,send_id,type,time_sent,0,show_id))
            conn.commit()
            return True
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get notification number
def get_notification_number(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            noti_number = c.execute("""SELECT noti_id FROM notifications WHERE user_read=0 AND rec_id IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))

            return noti_number
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get all notifications details
def get_all_notifications(uid):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT * FROM notifications WHERE rec_id = %s ORDER BY time_sent DESC""", (uid,))
            results = c.fetchall()
            print(results)
            all_noti_details = []

            #Loop to add name to details
            for x in results:
                x = list(x)

                #Find name
                c.execute("""SELECT name FROM accounts WHERE uid=%s""", (x[2]))
                name = c.fetchone()[0]

                #Calcuate time sent
                time_sent = cal_time_sent(x[4])

                #Add name and time
                x.append(name)
                x.append(time_sent)

                #Find notifcation type and get whats needed for link to that item
                noti_type = x[3]

                #If notification is a message
                if noti_type == 1:
                    c.execute("""SELECT thread_id FROM messages WHERE rec_id=%s AND send_id=%s""", (x[1],x[2],))
                    noti_type_results = c.fetchone()[0]

                    #Add noti_results
                    x.append(noti_type_results)

                #If notifcation is a bid
                elif noti_type == 2:
                    c.execute("""SELECT show_date FROM show_postings WHERE show_id=%s""", (x[6],))
                    noti_type_results = c.fetchone()

                    #Add show details
                    x.append(noti_type_results)

                #If notification is a winning bid offer
                elif noti_type == 3:
                    #Get venue name
                    c.execute("""SELECT business_name FROM venue_profile_details WHERE uid=%s""", (x[2],))
                    venue_business_name = c.fetchone()[0]

                    x.append(venue_business_name)

                    #Get show date and time
                    c.execute("""SELECT show_date FROM show_postings WHERE show_id=%s""", (x[6],))
                    show_details = c.fetchone()

                    x.append(show_details)

                #Add results to all_notis_details
                all_noti_details.append(x)

            return all_noti_details
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Delete notification
def delete_message_notification(email,send_id):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""DELETE FROM notifications WHERE send_id=%s AND type=1 AND rec_id IN (SELECT uid FROM accounts WHERE email=%s)""", (send_id,email,))
            conn.commit()
            return True
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Mark bid notification as read
def mark_notification_read(show_id):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""UPDATE notifications SET user_read=1 WHERE show_id=%s""", (show_id,))
            conn.commit()
            return True
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#-#-#-#-# LISTING & POSTING SECTION -------------------------------

#Upload show posting
def create_show_posting(uid, show_inputs):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Parse show inputs
            show_inputs = json.loads(show_inputs)

            #Create show_id
            show_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])

            #Check if show_id is unique
            show_id_unique = c.execute("""SELECT show_id FROM show_postings WHERE show_id=%s""",(show_id,))

            #Find a new show id if already used
            while show_id_unique > 0:
                show_id = ''.join([random.choice(string.ascii_uppercase + string.digits) for x in range(15)])
                show_id_unique = c.execute("""SELECT show_id FROM show_postings WHERE show_id=%s""",(show_id,))

            #Convert show time sting to date
            show_date = show_inputs['date'].replace('/', '-')
            show_date = datetime.datetime.strptime(show_date, '%m-%d-%Y')

            #Today's date
            date_posted = datetime.datetime.utcnow()

            #Show details
            show_post_details = (
                show_id,
                uid,
                show_inputs['price'],
                show_inputs['description'],
                show_inputs['artist_type'],
                show_inputs['location'],
                show_date,
                show_inputs['time'],
                show_inputs['set_length'],
                date_posted,
            )

            #Insert into show_postings
            c.execute("""INSERT INTO show_postings(show_id,uid,price,description,artist_type,location,show_date,show_time,set_length,date_posted) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", show_post_details)

            #Add genres
            if (len(show_inputs['genres']) != 0):
                for genre in show_inputs['genres']:
                    #Insert into show_genres
                    c.execute("""INSERT INTO show_genres(show_id,name) VALUES(%s,%s)""", (show_id, genre,))

            #Add requirements
            if (len(show_inputs['requirements']) != 0):
                for requirement in show_inputs['requirements']:
                    #Insert into show_requirements
                    c.execute("""INSERT INTO show_requirements(show_id,message) VALUES(%s,%s)""", (show_id, requirement,))

            #Add perks
            if (len(show_inputs['perks']) != 0):
                for perk in show_inputs['perks']:
                    #Insert into show_perks
                    c.execute("""INSERT INTO show_perks(show_id,message) VALUES(%s,%s)""", (show_id, perk,))

            conn.commit()

            return json.dumps({'success': 'show posted'})
        except Exception as e:
            traceback.print_exc()
            return json.dumps({'error': str(e)})
        finally:
            if conn:
                conn.close()

#Get venue show postings
def get_venue_show_postings(uid = None, ending_soon = None, limit = None):
    conn = connect_to_database()

    if conn is not False:
        c = conn.cursor()
        try:

            #If getting specific user's show postings
            if uid:

                #If getting shows ending soon
                if ending_soon:
                    two_weeks = datetime.datetime.today() + datetime.timedelta(days=14)

                    #Select shows that are open and ending soon
                    c.execute("""SELECT show_postings.*, venue_profile_details.business_name FROM show_postings, venue_profile_details WHERE venue_profile_details.uid = %s AND show_postings.uid = %s AND show_postings.won = 0 AND show_postings.show_date <= %s ORDER BY show_postings.show_date ASC LIMIT 5""", (uid, uid, two_weeks))
                else:
                    #Get list of posts by user
                    c.execute("""SELECT show_postings.*, venue_profile_details.business_name FROM show_postings, venue_profile_details WHERE show_postings.uid = %s AND venue_profile_details.uid = %s ORDER BY show_postings.show_date ASC""", (uid, uid))
            else:
                #Check for limit
                if limit is None:
                    limit = 10
                else:
                    limit = int(limit)

                #Get all show postings
                c.execute("""SELECT show_postings.*, venue_profile_details.business_name FROM show_postings, venue_profile_details WHERE show_postings.uid=venue_profile_details.uid ORDER BY show_postings.show_date ASC LIMIT %s""", (limit,))

            venue_show_postings = c.fetchall()

            #Another list of show postings so we can modify the real one without breaking Loop
            loop_postings = venue_show_postings
            venue_show_postings = []

            for x in loop_postings:

                show_details = {
                    'show_id': x[0],
                    'uid': x[1],
                    'price': x[2],
                    'description': x[3],
                    'artist_type': x[4],
                    'location': x[5],
                    'show_date': str(x[6].strftime("%b %d")),
                    'show_time': x[7],
                    'set_length': x[8],
                    'date_posted': str(x[9]),
                    'business_name': x[11],
                }

                #Check if there is already a winner for the show
                has_winner = c.execute("""SELECT * FROM show_bids WHERE show_id=%s AND winner=1""", x[0])

                if has_winner == 1:
                    show_details['show_status'] = "won"
                elif has_winner == 2:
                    show_details['show_status'] = "closed"
                else:
                    show_details['show_status'] = "open"

                venue_show_postings.append(show_details)

            return json.dumps({'success': venue_show_postings})
        except Exception as e:
            print (e)
            return json.dumps({'error': 'could not load show postings'})
        finally:
            if conn:
                conn.close()

#Get show details for one listing
def get_venue_one_show(show_id):

    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get show details
            c.execute("""SELECT show_postings.*, venue_profile_details.business_name FROM show_postings, venue_profile_details WHERE show_id = %s AND venue_profile_details.uid = show_postings.uid""", (show_id,))
            show_results = c.fetchall()[0]

            #Get show genres
            c.execute("""SELECT genre_id, name FROM show_genres WHERE show_id = %s""", (show_id,))
            genre_results = c.fetchall()

            #Get show perks
            c.execute("""SELECT id, message FROM show_perks WHERE show_id = %s""", (show_id,))
            perks_results = c.fetchall()

            #Get show requirements
            c.execute("""SELECT id, message FROM show_requirements WHERE show_id = %s""", (show_id,))
            requirements_results = c.fetchall()

            #List for genre, perks, requirements
            genres_list = []
            perks_list = []
            requirements_list = []

            #Loop through genres, convert to dict
            for x in genre_results:
                dict = {
                    'id': x[0],
                    'genre': x[1]
                }
                genres_list.append(dict)

            #Loop through perks, convert to dict
            for x in perks_results:
                dict = {
                    'id': x[0],
                    'perk': x[1]
                }
                perks_list.append(dict)

            #Loop through genres, convert to dict
            for x in requirements_results:
                dict = {
                    'id': x[0],
                    'requirement': x[1]
                }
                requirements_list.append(dict)

            show_details = {
                'show_id': show_results[0],
                'uid': show_results[1],
                'price': show_results[2],
                'description': show_results[3],
                'artist_type': show_results[4],
                'location': show_results[5],
                'show_date': str(show_results[6].strftime("%b %d")),
                'show_time': show_results[7],
                'set_length': show_results[8],
                'date_posted': str(show_results[9]),
                'business_name': show_results[11],
                'genres': genres_list,
                'perks': perks_list,
                'requirements': requirements_list,
            }


            return show_details
        except Exception as e:
            print (e)
            return "Could not load results"
        finally:
            if conn:
                conn.close()

#Get venue information for single listing
def get_listing_profile_details(uid):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get venue details
            c.execute("""SELECT * FROM venue_profile_details WHERE uid=%s""", (uid,))
            venue_details = c.fetchone()
            return venue_details
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#----SPOTIFY SECTION ---------------------------------------
#Add user Spotify auth token to table
def set_spotify_access_token(email,spotify_auth_code):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Find user id
            find_user = c.execute("""SELECT uid FROM accounts WHERE email=%s""", (email,))

            if find_user == 1:
                uid = c.fetchone()[0]

                #Body info
                client_id = "c74d1fc0c128497b8e42890d5fc900bf"
                client_secret = "42d3e37e256a4f728b7df6da001249f6"
                uri = "https://www.blufftour.com/setuplinks"
                payload = {'grant_type':'authorization_code','code':spotify_auth_code,'redirect_uri':uri, 'client_id':client_id,'client_secret':client_secret}

                response = requests.post("https://accounts.spotify.com/api/token", data=payload)
                response_data = json.loads(response.text)
                access_token = response_data['access_token']
                refresh_token = response_data['refresh_token']

                #Update Spotify Auth token
                c.execute("""UPDATE spotify_access_tokens SET access_token=%s, refresh_token=%s WHERE uid=%s""", (access_token,refresh_token,uid,))
                conn.commit()
                return True
            else:
                return False
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Check Spotify user auth token
def check_spotify_access_token(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT access_token FROM spotify_access_tokens WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            spotify_auth_token = c.fetchone()[0]

            if spotify_auth_token is not None:
                return True
            else:
                return False

        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get Spotify user auth token
def get_spotify_access_token(email):
    #Connect to database
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            c.execute("""SELECT access_token FROM spotify_access_tokens WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            spotify_auth_token = c.fetchone()[0]

            if spotify_auth_token is not None:
                return spotify_auth_token
            else:
                return False
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Refresh Spotify access token
def refresh_spotify_token(email):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get refresh token from old access code
            c.execute("""SELECT refresh_token FROM spotify_access_tokens WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (email,))
            refresh_token = c.fetchone()[0]

            #Request data
            client_id = "c74d1fc0c128497b8e42890d5fc900bf"
            client_secret = "42d3e37e256a4f728b7df6da001249f6"
            payload = {
                "grant_type":"refresh_token",
                "refresh_token":refresh_token,
                "client_id":client_id,
                "client_secret":client_secret
            }

            #POST request for new one
            response = requests.post("https://accounts.spotify.com/api/token", data=payload)
            response_data = json.loads(response.text)
            access_token = response_data['access_token']

            #Save new access_token
            c.execute("""UPDATE spotify_access_tokens SET access_token=%s WHERE uid IN (SELECT uid FROM accounts WHERE email=%s)""", (access_token,email,))
            conn.commit()
            return True
        except Exception as e:
            print (e)
            return False
        finally:
            if conn:
                conn.close()

#Get Spotify account id
def get_spotify_account_uri(email):
    conn = connect_to_database()
    if conn is not False:
        c = conn.cursor()
        try:
            #Get user access token
            access_token = get_spotify_access_token(email)
            #Headers for requests
            headers = {"Authorization":"Bearer "+access_token}
            #Make request for account info
            response = requests.get("https://api.spotify.com/v1/me", headers=headers)

            #Refresh token if expired
            if response.status_code == 401:
                #Refresh token
                refresh_spotify_token(email)
                #Make request again
                response = requests.get("https://api.spotify.com/v1/me", headers=headers)

            response_data = json.loads(response.text)
            spotify_user_uri = response_data['uri']

            return spotify_user_uri
        except Exception as e:
            return False
        finally:
            if conn:
                conn.close()

#Get user Spotify follower count
def get_spotify_follower_count(email):
    spotify_user_uri = get_spotify_account_uri(email)
    access_token = get_spotify_access_token(email)
    spotify_user_uri = get_spotify_account_uri(email)
    headers = {"Authorization":"Bearer "+access_token}

    response = requests.get("https://api.spotify.com/v1/artists/"+spotify_user_uri, headers= headers)

    print (json.loads(response.content))

    if response.status_code == 200:
        response = json.loads(response.content)

        follower_count = response['followers']['total']
        return json.dumps({'success': follower_count})
    else:
        return json.dumps({'error': response})

#Get user Spotify top tracks
def get_spotify_top_tracks(email):
    spotify_user_uri = get_spotify_account_uri(email)
    access_token = get_spotify_access_token(email)
    spotify_user_uri = get_spotify_account_uri(email)
    headers = {"Authorization":"Bearer "+access_token}

    spotify_user_uri = "3TVXtAsR1Inumwj472S9r4"

    response = requests.get("https://api.spotify.com/v1/artists/"+spotify_user_uri+"/top-tracks?market=US", headers=headers)
    response_data = json.loads(response.text)

    if response.status_code == 200:
        #Top songs list with links in it
        spotify_top_tracks = []

        for x in response_data['tracks'][:3]:
            link = x['uri'].split(':',)[2]
            spotify_top_tracks.append(link)

        return json.dumps({"success": spotify_top_tracks})
    else:
        return json.dumps({"error": "no tracks"})

#Get user Spotify albums
def get_spotify_albums(email):
    spotify_user_uri = get_spotify_account_uri(email)
    access_token = get_spotify_access_token(email)
    spotify_user_uri = get_spotify_account_uri(email)
    headers = {"Authorization":"Bearer "+access_token}

    spotify_user_uri = "3TVXtAsR1Inumwj472S9r4"

    response = requests.get("https://api.spotify.com/v1/artists/"+spotify_user_uri+"/albums?market=US&limit=3", headers=headers)
    response_data = json.loads(response.text)

    if response.status_code == 200:
        spotify_albums = []

        for x in response_data['items']:
            album_link = x['external_urls']['spotify']
            album_picture = x['images'][1]['url']
            spotify_albums.append([album_link,album_picture])

        return json.dumps({"success": spotify_albums})
    else:
        return json.dumps({"error": "no albums"})


#-#-#-#- STRIPE PAYMENTS -#-#-#-#-#-#------------------------

#Stripe API PRIVATE KEY (DO NOT SHARE)
stripe.api_key = os.getenv('STRIPE_API_SECRET_KEY')

#Create Stripe account for customer
def create_stripe_account(email, account_type, account_details):
    try:
        #If account is an artist
        if account_type == 'artist':

            #Stripe Account Details
            firstName = account_details['firstName']
            lastName = account_details['lastName']
            birthday = account_details['birthday']
            ssn = account_details['SSN']
            tos_acceptance = account_details['tos_acceptance']
            ip_address = account_details['ip_address']
            payment_token = account_details['payment_token']

            #Format birthday
            split_birthday = birthday.split("/")
            birthday_month = split_birthday[0]
            birthday_day = split_birthday[1]
            birthday_year = split_birthday[2]

            #Create stripe account
            result = stripe.Account.create(
                type = "custom",
                country = "US",
                business_type = "individual",
                business_profile = {
                    'product_description': "Musician"
                },
                email = email,
                requested_capabilities = ['platform_payments'],
                tos_acceptance = {
                    'date': datetime.datetime.now(),
                    'ip': ip_address
                },
                individual = {
                    'first_name': firstName,
                    'last_name': lastName,
                    'dob': {
                        'day': birthday_day,
                        'month': birthday_month,
                        'year': birthday_year
                    },
                    'ssn_last_4': ssn,
                    'email': email
                },
                settings = {
                    'payouts': {
                        "schedule": {
                            "interval": "manual",
                        }
                    }
                },
                external_account = payment_token
            );

        else:
            #Create Venue stripe account

            #Account details
            businessName = account_details['businessName']
            paymentName = account_details['paymentName']
            payment_token = account_details['payment_token']

            #Create stripe account
            result = stripe.Customer.create(
                name = businessName,
                email = email,
                source = payment_token,
            );


        #If Stripe account was created
        if result:
            #Connect to database
            conn = connect_to_database()

            if conn is not False:
                c = conn.cursor()

                #Get uid
                uid = get_uid(email)

                #Stripe account id
                stripe_account_id = result.id

                #Insert into paymentAaccounts table
                c.execute("""UPDATE payment_accounts SET stripe_account_id = %s, has_funding = %s WHERE uid = %s""", (stripe_account_id,1,uid,))
                conn.commit()

                result = "success"
        else:
            result = "Could not create Stripe account"

        #Return status
        return json.dumps({"result": result})

    except Exception as e:
        result = str(e)
        print (result)

        #Check if credit card error
        if "This card doesn't appear to be a debit card" in result:
            result = "This card doesn't appear to be a debit card"
        else:
            result = "Could not create payment account"

        return json.dumps({"result": result})

#Add new Stripe payment method
def create_stripe_payment_method(email, account_type, payment_token):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get uid
            uid = get_uid(email)

            #Get Stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            if account_type == "artist":

                #Add card to stripe
                new_payment = stripe.Account.create_external_account(
                    stripe_account_id,
                    external_account = payment_token
                )
            else:
                #Add card to stripe
                new_payment = stripe.Customer.create_source(
                    stripe_account_id,
                    source = payment_token
                )

            #Type of payment method added
            payment_type = new_payment.object

            if (payment_type == "card"):
                result = "Successfully added debit card"
            else:
                result = "Successfully added bank account"

            return json.dumps({'success': result})

    except stripe.error.StripeError as error:
        error_code = error.code

        #If card was declined
        if error_code == "card_declined":

            #If not enough funds
            if "insufficient funds" in str(error):
                error_code = "This card has insufficient funds"
            else:
                error_code = "This card was declined"

        #If card is expired
        if error_code == "expired_card":
            error_code = "This card is expired"

        #If card has incorrect CVC
        if error_code == "incorrect_cvc":
            error_code = "This card's security code is incorrect"

        #If there was an proccessing error
        if error_code == "processing_error":
            error_code = "An error occurred while processing your card. Try again in a little bit"

        #If card is a credit card
        if error_code == "invalid_card_type":
            error_code = "Must be a debit card"

        return json.dumps({"error": error_code})

    except Exception as e:
        print (e)
        return json.dumps({'error': 'Error while processing card'})
    finally:
        if conn:
            conn.close()

#Verify bank account payment method
def verify_bank_payment_method(email, payment_id, micro_amount1, micro_amount2):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get uid
            uid = get_uid(email)

            #Get stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            #Get stripe account
            customer = stripe.Customer.retrieve(stripe_account_id)

            #Parse payment id
            payment_id = payment_id.split("-")[1]

            #Get bank payment method
            bank_account = customer.sources.retrieve(payment_id)

            #Verify bank account
            verify_result = bank_account.verify(amounts = [micro_amount1, micro_amount2])

            #Check if verification was good
            if verify_result.status == 'verified':
                result = {"success": "Bank account has been verified"}
            else:
                result = {"error": "There was an issue verifying this bank account"}

            return json.dumps(result)

    #Stripe failure
    except stripe.error.StripeError as error:
        error = str(error).split(":")[1].lstrip(" ")

        #If verification has already happended
        if "This bank account has already been verified." in error:
            result = {"prev_completed": error}
        #If verification amounts were incorrect
        elif "The amounts provided do not match the amounts that were sent to the bank account." in error:
            result = {"failed": error}
        #If unknown stripe error
        else:
            result = {"error": error}

        #Return result
        return json.dumps(result)

    #Unexpected failure
    except Exception as e:
        print (e)
        return json.dumps({"error": "Error while verifying account"})
    finally:
        if conn:
            conn.close()

#Delete Stripe card payment method
def delete_stripe_payment_method(email, account_type, payment_id):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get uid
            uid = get_uid(email)

            #Get stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            if account_type == "artist":
                #Delete card from stripe
                stripe.Account.delete_external_account(
                    stripe_account_id,
                    payment_id
                )
            else:
                #Delete card from stripe
                stripe.Customer.delete_source(
                    stripe_account_id,
                    payment_id
                )

            result = "Payment deleted"

            return json.dumps({'success': result})

    #Stripe failure
    except stripe.error.StripeError as error:
        error = str(error).split(":")[1].lstrip(" ")

        #If default payment method
        if "cannot delete the default external account" in error:
            result = {"error": "You cannot delete the default payment method for your account."}
        #If card is deleted and redeleted?
        elif "has been deleted and can no longer be used" in error:
            print (error)
            result = {"error": "Error: This payment method has already been removed from your account!"}
        else:
            print (error)
            result = {"error": error}

        return json.dumps(result)

    except Exception as e:
        print (e)
        return json.dumps({'error': 'could not delete payment'})
    finally:
        if conn:
            conn.close()

#Check for stripe account
def check_stripe_account(email):

    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get uid
            uid = get_uid(email)

            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            account_check = c.fetchone()[0]

            if account_check is None:
                result = "No account"
            else:
                result = "Has account"

            return json.dumps({"result": result})

    except Exception as e:
        print (e)
        return json.dumps({"error": "There was a problem connecting to Stripe"})
    finally:
        if conn:
            conn.close()

#Check if Stripe Account has a payment method
def check_stripe_payment_method(email, account_type):
    try:
        #Connect to database
        conn = connect_to_database()

        print ("nipple")

        if conn is not False:
            c = conn.cursor()

            #Get uid
            uid = get_uid(email)

            #Get stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid=%s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            #Venue account type
            if account_type == "venue":
                #Get payment sources from Stripe for venue
                payment_methods = stripe.Customer.retrieve(
                    stripe_account_id
                )

                #Payment methods
                number_payment_methods = len(payment_methods['sources']['data'])
            else:
                #Artist account type

                #Get payment sources from Stripe for artist
                payment_methods = stripe.Account.list_external_accounts(
                    stripe_account_id
                )

                #Payment methods
                number_payment_methods = len(payment_methods['data'])

            #If there is a payment method return good
            if number_payment_methods != 0:
                result = "has_payment"
            else:
                result = "no_payment"

            #Return result
            return json.dumps({'result': result})

    except Exception as e:
        print (e)
        return json.dumps({'result':"error checking payment source"})
    finally:
        if conn:
            conn.close()

#Charge venue for show
def charge_stripe_venue_payment(show_id):
    try:
        #Connect to database
        conn = connect_to_database()

        #If database connection was good
        if conn is not False:
            c = conn.cursor()

            #Get details from payment transactions
            c.execute("""SELECT venue_id, artist_id, show_price, show_date FROM payment_transactions WHERE show_id=%s""", (show_id,))
            query_result = c.fetchone()

            #Party details
            venue_uid = query_result[0]
            artist_uid = query_result[1]

            #Show date
            show_date = query_result[3].strftime("%b %d, %Y")

            #Price that venue will be charged for
            transaction_price = query_result[2]

            #Get Stripe account ID for Venue
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid=%s""", venue_uid,)
            venue_stripe_account_id = c.fetchone()[0]

            #Get payment method for venue
            payment_methods = stripe.Customer.retrieve(
                venue_stripe_account_id
            )
            payment_methods = payment_methods['sources']['data']

            #If Venue has a Stripe payment method
            if len(payment_methods) != 0:

                #Venue email, used for stripe receipt
                venue_email = get_email(venue_uid)

                #Get artist Stripe account id and Name
                c.execute("""SELECT payment_accounts.stripe_account_id, accounts.name FROM payment_accounts, accounts WHERE payment_accounts.uid= %s AND accounts.uid = payment_accounts.uid""", (artist_uid,))
                artist_details = c.fetchone()
                artist_stripe_account_id = artist_details[0]
                artist_name = artist_details[1]

                #What the customer is charged
                total_fee = int(transaction_price * .07)

                #Make stripe transaction
                charge = stripe.Charge.create(
                    amount = transaction_price,
                    currency = "usd",
                    description = "You paid "+artist_name+" for the show on "+str(show_date),
                    receipt_email = venue_email,
                    customer = venue_stripe_account_id,
                    transfer_data = {
                        "destination": artist_stripe_account_id,
                    },
                    application_fee_amount = total_fee,
                )

                #If charge was successful
                if charge['status'] == 'succeeded':

                    #Stripe transition id
                    stripe_transaction_id = charge['id']
                    stripe_transaction_balance_id = charge['balance_transaction']

                    #What stripe gets
                    stripe_fee = int((transaction_price * .029) + 30)
                    #What we take home
                    our_take_home = int(total_fee - stripe_fee)

                    #Update transaction row
                    c.execute("""UPDATE payment_transactions SET stripe_transaction_id = %s, stripe_balance_transaction_id = %s, total_fee_charged = %s, stripe_fee = %s, bluff_fee = %s, status="Holding payment" WHERE show_id=%s""", (stripe_transaction_id, stripe_transaction_balance_id, total_fee, stripe_fee, our_take_home, show_id,))
                    conn.commit()

                    return json.dumps({'show_id': show_id,'result': 'success'})

                else:
                    result = charge['status']
            else:
                result = "no_payment"

            return json.dumps({'show_id': show_id,'result': 'error', 'reason': result})

        else:
            return json.dumps({'show_id': show_id,'result': 'error', 'reason': "Could not connect to the database"})

    except Exception as e:

        print (e)
        return json.dumps({'show_id': show_id,'result': 'error', 'reason': repr(e)})
    finally:
        if conn:
            conn.close()

#Create payout for artist
def create_stripe_payout_artist(artist_uid, cashout_method):
    try:
        #Connect to database
        conn = connect_to_database()

        #If connected to database
        if conn is not False:
            c = conn.cursor()

            #Get artist stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (artist_uid,))
            artist_stripe_account_id = c.fetchone()[0]

            #If stripe account has been created
            if artist_stripe_account_id is not None:

                #Get available balance from stripe
                account_balances = json.loads(get_stripe_account_balance(artist_uid))
                available_balance = account_balances['result']['available_balance']

                if available_balance != 0:

                    #Parse cashout_method to find card/bank and instant or standard
                    cashout_method_details = cashout_method.split("_")
                    cashout_type = cashout_method_details[0]
                    cashout_destination = cashout_method_details[2]

                    #Get payment methods
                    payment_methods = stripe.Account.retrieve(
                        artist_stripe_account_id
                    )['external_accounts']['data']

                    #Validate cashout destination is from that artist
                    validated_cashout_destination = False

                    for x in payment_methods:
                        payment_method_id = x['id'].split("_")[1]

                        if (payment_method_id == cashout_destination):
                            validated_cashout_destination = True
                            cashout_destination = x['id']
                            cashout_account_type = x['object']
                        else:
                            pass

                    if validated_cashout_destination:

                        #Payout funds to artist bank account
                        payout_funds = stripe.Payout.create(
                            stripe_account = artist_stripe_account_id,
                            amount = available_balance,
                            currency = "usd",
                            destination = cashout_destination,
                            source_type = cashout_account_type,
                            method = cashout_type,
                        )

                        if payout_funds:

                            #Update transaction records
                            # c.execute("""UPDATE payment_transactions SET status = 'payout' WHERE show_id = %s""",(show_id,))
                            # conn.commit()

                            result = "Payout completed"
                    else:
                        result = "No payment method associated with this account"
                else:
                    result = "No funds available to be sent"
            else:
                result = "Need payment account"

            return json.dumps({"result": result})

    #If stripe error
    except stripe.error.StripeError as error:
        print (error)
        error_code = error.code
        return json.dumps({"result": error_code})

    except Exception as error:
        print (error)
        result = "There was an error proccessing your request"
        return json.dumps({"result": result})
    finally:
        if conn:
            conn.close()

#Get artist Stripe account balance (Money that they will get after the show)
def get_stripe_account_balance(uid):
    try:
        #Connect to Database
        conn = connect_to_database()

        #Connected to database
        if conn is not False:
            c = conn.cursor()

            #Get stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            #If stripe account has been created
            if stripe_account_id is not None:

                #Get stripe account balance
                account_balance = stripe.Balance.retrieve(
                    stripe_account = stripe_account_id
                )

                available_balance = account_balance['available'][0]['amount']
                pending_balance = account_balance['pending'][0]['amount']

                result = {
                    'available_balance': available_balance,
                    'pending_balance': pending_balance,
                }
            else:
                result = "Need create payment account"

            return json.dumps({"result": result})
    except Exception as e:
        print (e)
        return False
    finally:
        if conn:
            conn.close()

#Get Stripe payment methods for user
def get_stripe_payment_methods(uid, account_type):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get Stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid,))
            stripe_account_id = c.fetchone()[0]

            if stripe_account_id != None:
                #Artist account
                if account_type == "artist":
                    #Get payment methods
                    payment_methods = stripe.Account.retrieve(
                        stripe_account_id
                    )

                    #Artist payment methods
                    payment_methods = payment_methods['external_accounts']['data']
                else:
                    #Get payment methods
                    payment_methods = stripe.Customer.retrieve(
                        stripe_account_id
                    )

                    #Venue payment methods
                    payment_methods = payment_methods['sources']['data']

                #All payments container
                all_payment_methods = {
                    "card": [],
                    "bank_account": []
                }

                #Loop through all payment methods
                for x in payment_methods:

                    #Get payment
                    payment_type = x["object"]

                    if payment_type == "card":

                        #Card details
                        card_details = {}
                        card_details["card_id"] = x['id']
                        card_details["card_brand"] = x['brand']
                        card_details["card_type"] = str(x['funding']).capitalize()
                        card_details["card_last4"] = x['last4']
                        card_details["expire_month"] = x['exp_month']
                        card_details["expire_year"] = str(x['exp_year'])[2:4]

                        #If artist, check payout status
                        if account_type == "artist":
                            card_details["instant_payout"] = False

                            #If has instant payout method
                            if 'instant' in x['available_payout_methods']:
                                card_details["instant_payout"] = True

                            #If default payment method
                            if x['default_for_currency']:
                                card_details['default'] = True
                            else:
                                card_details['default'] = False

                        #Add details to payment methods object
                        all_payment_methods['card'].append(card_details)
                    else:
                        bank_details = {}
                        bank_details['bank_id'] = x['id']
                        bank_details['bank_name'] = x['bank_name']
                        bank_details['bank_last4'] = x['last4']
                        bank_details['bank_status'] = x['status']

                        if account_type == "artist":
                            #If default payment method
                            if x['default_for_currency']:
                                bank_details['default'] = True
                            else:
                                bank_details['default'] = False

                        #Add details to payment methods object
                        all_payment_methods['bank_account'].append(bank_details)

                return json.dumps(all_payment_methods)
            else:
                result = "No account"
        else:
            result = "Could not retrieve payment details"

        return json.dumps({'result': result})
    except Exception as e:
        print (e)
        return json.dumps({'result': str(e)})
    finally:
        if conn:
            conn.close()

#Get artist payout transactions
def get_stripe_payouts(artist_uid, starting_after = None):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get artist stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (artist_uid))
            artist_stripe_account_id = c.fetchone()[0]

            if artist_stripe_account_id is not None:

                #Get stripe payouts
                stripe_payouts = stripe.Payout.list(
                    stripe_account = artist_stripe_account_id,
                    limit = 5,
                    starting_after = starting_after,
                )

                #List to store all payouts
                stripe_payouts_list = []

                #Artist stripe account
                stripe_account = stripe.Account.retrieve(artist_stripe_account_id)

                #Loop through list and get needed details
                for payout in stripe_payouts:

                    #Find external account details
                    external_account = stripe_account.external_accounts.retrieve(payout['destination'])

                    if external_account['object'] == "card":
                        external_account_details = {
                            'brand': external_account['brand'],
                            'last4': external_account['last4']
                        }
                    else:
                        external_account_details = {
                            'bank_name': external_account['bank_name'],
                            'last4': external_account['last4']
                        }

                    single_payout = {
                        'id': payout['id'],
                        'object': external_account['object'],
                        'amount': payout['amount'],
                        'method': payout['method'].capitalize(),
                        'status': payout['status'].capitalize(),
                        'external_account': external_account_details,
                        'date': datetime.datetime.utcfromtimestamp(payout['created']).strftime('%m/%d/%Y'),
                    }

                    stripe_payouts_list.append(single_payout)

                result = stripe_payouts_list

            else:
                result = "No stripe account"

            return json.dumps({'result': result})
        else:
            raise Exception("Could not connect to database")

    except Exception as e:
        print (e)
        return json.dumps({'result': 'Could not retrieve payout transactions'})
    finally:
        if conn:
            conn.close()

#Get Stripe charges for user
def get_stripe_charges(uid, starting_after = None):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid))
            stripe_account_id = c.fetchone()[0]

            if stripe_account_id is not None:

                #Get stripe transactions
                stripe_transactions = stripe.Charge.list(
                    customer = stripe_account_id,
                    limit = 5,
                    starting_after = starting_after
                )

                #Transactions list
                all_transactions = []

                #Loop through all transactions
                for charge in stripe_transactions:

                    #Get artist name
                    artist = c.execute("""SELECT accounts.name, payment_transactions.show_id FROM accounts, payment_transactions WHERE payment_transactions.stripe_transaction_id = %s""", (charge['id']))

                    #If artist name is found (Should ALWAYS find it)
                    if artist != 0:
                        artist_name = c.fetchone()[0]
                        show_id = c.fetchone()[1]
                    else:
                        artist_name = "boob"
                        show_id = "penis"

                    single_charge = {
                        "id": charge["id"],
                        "amount": charge['amount'],
                        "payment_type": charge['payment_method_details']['type'],
                        "status": charge['status'],
                        "transaction_date": datetime.datetime.utcfromtimestamp(charge['created']).strftime('%m/%d/%Y'),
                        "receipt_url": charge['receipt_url'],
                        "show_id": show_id,
                        "artist": artist_name,
                    }

                    all_transactions.append(single_charge)

            return json.dumps({'success': all_transactions})

    except Exception as e:
        print (e)
        return json.dumps({'error': 'Error retrieving payment transactions'})
    finally:
        if conn:
            conn.close()

#Get Stripe balance transactions
def get_stripe_payment_transactions(uid, starting_after = None):
    try:
        #Connect to database
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Get stripe account id
            c.execute("""SELECT stripe_account_id FROM payment_accounts WHERE uid = %s""", (uid))
            stripe_account_id = c.fetchone()[0]

            if stripe_account_id is not None:

                #Get stripe transactions
                stripe_payments = stripe.BalanceTransaction.list(
                    stripe_account = stripe_account_id,
                    type = 'payment',
                    limit = 5,
                    starting_after = starting_after
                )

                #Transactions list
                all_payments = []

                #Loop through all transactions
                for payment in stripe_payments:
                    print (payment)

                    payment_details = {
                        'id': payment['id'],
                        'net_amount': payment['net'],
                        'date': datetime.datetime.utcfromtimestamp(payment['created']).strftime('%m/%d/%Y'),
                        'available': datetime.datetime.utcfromtimestamp(payment['available_on']).strftime('%m/%d/%Y'),
                        'status': payment['status'],
                    }

                    all_payments.append(payment_details)


            return json.dumps({'success': all_payments})

    except Exception as e:
        print (e)
        return json.dumps({'error': 'Error retrieving payment transactions'})
    finally:
        if conn:
            conn.close()
