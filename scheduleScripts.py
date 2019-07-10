from venueimports import datetime
from venueimports import string
from venueimports import random
from venueimports import time
from venueimports import pymysql
import os
import time
import venuehandler
import boto3
from botocore.client import Config
from dotenv import load_dotenv
import json

#Load env variables
load_dotenv('test.env')

#Connect to database
def connect_to_database():
    try:
        #mysql path C:\Program Files\MySQL\MySQL Server 8.0\bin
        conn = pymysql.connect(
            host= os.getenv('DATABASE_LOCATION'),
            db= os.getenv('DATABASE_NAME'),
            user= os.getenv('DATABASE_USERNAME'),
            password= os.getenv('DATABASE_PASSWORD'),
        )
        return conn
    except Exception as e:
        print (e)

        #Log shows closed
        logging.basicConfig(
            filename='logs/Automated_logs/mysql_error_'+str(datetime.date.today())+'.txt',
            filemode='a+',
            format='%(message)s',
        )
        logging.error(e)

        #Send to AWS
        log_type = "mysql_error_"+str(datetime.date.today())+".txt"
        write_log_AWS(log_type)

        conn = False
        return conn

#Write log to AWS bucket
def write_log_AWS(log_type):
    log_data = open("logs/Automated_logs/"+log_type, "rb")

    log_path = "logs/Automated_logs/"+log_type

    #AWS client setup
    s3 = boto3.resource(
        's3',
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.getenv('AWS_ACCESS_SECRET_KEY'),
        config = Config(signature_version = 's3v4')
    )

    #Write file to AWS S3 bucket
    s3.Bucket(os.getenv('AWS_BUCKET_NAME')).put_object(Key = log_path, Body = log_data, ContentType = 'text/html')

    return True

#Check if show is within 7 days of happening, close show
def check_show_7_close():
    try:
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #Log filename
            log_filename= 'logs/Automated_logs/7DaysTill/'+str(datetime.date.today())+'.txt'

            one_week_away = datetime.datetime.today() + datetime.timedelta(days=7)

            #Get all shows that are happening in 24 hours
            c.execute("""SELECT * FROM show_postings WHERE show_date <= %s AND won = 0""", one_week_away)
            upcoming_shows = c.fetchall()

            #Check if at least 1 show ending
            if len(upcoming_shows) != 0:

                #loop through all shows and handle
                for show in upcoming_shows:

                    #Close show, notify venue
                    c.execute("""UPDATE show_postings SET won = 2 WHERE show_id  = %s""", (show[0]))

                    #Log closing show
                    with open(log_filename, 'a') as log_file:
                        log_file.write("Show id:"+show[0]+"- closed, no bids 7 days before showdate\n")

                #Save deletions
                conn.commit()
            else:
                #Log no shows closed
                with open(log_filename, 'a') as log_file:
                    log_file.write("No shows were closed")

            #Send logs to AWS
            log_type = "7DaysTill/"+str(datetime.date.today())+".txt"
            write_log_AWS(log_type)

            return True


    except Exception as e:
        #Log filename
        log_filename='logs/Automated_logs/7DaysTill/error_'+str(datetime.date.today())+'.txt',

        #Log the error
        with open(log_filename, 'a') as log_file:
            log_file.write(e)

        #Send to AWS
        log_type = "7DaysTill/error_"+str(datetime.date.today())+".txt"
        write_log_AWS(log_type)
    finally:
        if conn:
            conn.close()

#Used to check if show is about to happen
def check_playing_shows():
    try:
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #24 hours away
            next_24 = datetime.datetime.today() + datetime.timedelta(days=1)

            #Get all shows that are happening in 24 hours
            c.execute("""SELECT * FROM show_postings WHERE show_date <= %s""", (next_24))
            upcoming_shows = c.fetchall()

            if len(upcoming_shows) != 0:

                #loop through all shows and handle
                for show in upcoming_shows:
                    #Charge the venue for the show
                    result = venuehandler.charge_stripe_venue_payment(show[0])

                    result = json.loads(result)

                    #If charged show successfully
                    if result['result'] == "success":

                        #Log filename
                        log_filename='logs/Automated_logs/24HoursBefore/shows_success_'+str(datetime.date.today())+'.txt',

                        #Log result
                        with open(log_filename, 'a') as log_file:
                            log_file.write("Show id:"+show[0]+"- venue has been charged\n")

                        #Send to AWS
                        log_type = "24HoursBefore/shows_success_"+str(datetime.date.today())+".txt"
                        write_log_AWS(log_type)
                    else:
                        #Log filename
                        log_filename='logs/Automated_logs/24HoursBefore/shows_error_'+str(datetime.date.today())+'.txt',

                        #Log result
                        with open(log_filename, 'a') as log_file:
                            log_file.write("Show id:"+str(show[0])+"- error: "+str(result['reason'])+"\n")

                        #Send to AWS
                        log_type = "24HoursBefore/shows_error_"+str(datetime.date.today())+".txt"
                        write_log_AWS(log_type)
            else:
                #Log filename
                log_filename= 'logs/Automated_logs/24HoursBefore/shows_success_'+str(datetime.date.today())+'.txt'

                #Log result
                with open(log_filename, 'a') as log_file:
                    log_file.write("No shows are being performed, no billing changed")

                #Send to AWS
                log_type = "24HoursBefore/shows_success_"+str(datetime.date.today())+".txt"
                write_log_AWS(log_type)

    except Exception as e:
        #Log filename
        log_filename='logs/Automated_logs/24HoursBefore/error_'+str(datetime.date.today())+'.txt',

        #Log error
        with open(log_filename, 'a') as log_file:
            log_file.write(str(e))

        #Send to AWS
        log_type = "24HoursBefore/error_"+str(datetime.date.today())+".txt"
        write_log_AWS(log_type)
    finally:
        if conn:
            conn.close()

#Check if transaction had a dispute, if not change status to paid
def check_pay_artist_ready():
    try:
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            #24 hours ago
            last_24 = datetime.datetime.today() - datetime.timedelta(days=1)

            #Get all shows that happened in 24 hours
            c.execute("""SELECT * FROM payment_transactions WHERE show_date <= %s""", (last_24))
            finished_shows = c.fetchall()

            if len(finished_shows) != 0:
                #Loop through all show transactions
                for show in finished_shows:
                    show_id = show[0]
                    transation_status = show[10]

                    if (transation_status == "Holding payment"):
                        #Update transaction status to finished
                        c.execute("""UPDATE payment_transactions SET status = "finished" WHERE show_id  = %s""", (show_id))
                        conn.commit()

                        #Log filename
                        log_filename='logs/Automated_logs/24HoursAfter/completed_'+str(datetime.date.today())+'.txt',

                        #Log result
                        with open(log_filename, 'a') as log_file:
                            log_file.write("Show id:"+show_id+", has be finished, artist will be paid\n")

                        #Send to AWS
                        log_type = "24HoursAfter/completed_"+str(datetime.date.today())+".txt"
                        write_log_AWS(log_type)
            else:
                #Log filename
                log_filename='logs/Automated_logs/24HoursAfter/completed_'+str(datetime.date.today())+'.txt'

                #Log result
                with open(log_filename, 'a') as log_file:
                    log_file.write("No transactions changed, no artists paid")

                #Send to AWS
                log_type = "24HoursAfter/completed_"+str(datetime.date.today())+".txt"
                write_log_AWS(log_type)

    except Exception as e:
        #Log filename
        log_filename='logs/Automated_logs/24HoursAfter/error_'+str(datetime.date.today())+'.txt',

        #Log error
        with open(log_filename, 'a') as log_file:
            log_filename.write(e)

        #Send to AWS
        log_type = "24HoursAfter/error_"+str(datetime.date.today())+".txt"
        write_log_AWS(log_type)
    finally:
        if conn:
            conn.close()

check_show_7_close()
check_playing_shows()
check_pay_artist_ready()
