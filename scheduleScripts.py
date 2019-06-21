from venueimports import datetime
from venueimports import string
from venueimports import random
from venueimports import time
from venueimports import pymysql

#Connect to database
def connect_to_database():
    try:
        #mysql path C:\Program Files\MySQL\MySQL Server 8.0\bin
        conn = pymysql.connect(
            host= os.environ['CLEARDB_DATABASE_LOCATION'], #External IP 99.114.66.154 Local IP 192.168.1.111
            db= os.environ['CLEARDB_DATABASE_DB'],
            user= os.environ['CLEARDB_DATABASE_USERNAME'], #jeffbezos
            password= os.environ['CLEARDB_DATABASE_PASSWORD'], #alexa
        )
        return conn
    except Exception as e:
        print (e)
        print ("Could not connect database")
        conn = False
        return conn

#Check if show is within 7 days of happening, close show
def check_show_7_close():
    try:
        conn = connect_to_database()

        if conn is not False:
            c = conn.cursor()

            one_week_away = datetime.datetime.today() + datetime.timedelta(days=7)

            #Get all shows that are happening in 24 hours
            c.execute("""SELECT * FROM show_postings WHERE show_date <= %s AND won = 0""", one_week_away)
            upcoming_shows = c.fetchall()

            #loop through all shows and handle
            for show in upcoming_shows:
                #Close show, notify venue
                c.execute("""UPDATE show_postings SET won = 2 WHERE show_id  = %s""", (show[0]))

            #Save deletions
            conn.commit()

    except Exception as e:
        print (e)
        return {'error': e}
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

            #loop through all shows and handle
            for show in upcoming_shows:
                #Charge the venue for the show
                result = charge_stripe_venue_payment(show[0])

                result = json.loads(result)

                if result['result'] == "success":
                    #Log for checking if script ran properly
                    log = open("Automated Logs/daily_charge_script.txt", "a")
                    log.write(result['show_id']+", Success, "+str(datetime.datetime.now())+"\n")
                    log.close()
                else:
                    log = open("Automated logs/daily_charge_script_error.txt", "a")
                    log.write(result['show_id']+", Error: "+result['reason']+", "+str(datetime.datetime.now())+"\n")
                    log.close()

    except Exception as e:

        log = open("Automated logs/daily_charge_script_disater.txt", "a")
        log.write("Error: "+ e +", "+str(datetime.datetime.now())+"\n")
        log.close()
    finally:
        if conn:
            conn.close()

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

            #Loop through all show transactions
            for show in finished_shows:
                show_id = show[0]
                transation_status = show[10]

                if (transation_status == "Holding payment"):
                    #Update transaction status to finished
                    c.execute("""UPDATE payment_transactions SET status = "finished" WHERE show_id  = %s""", (show_id))
                    conn.commit()

    except Exception as e:

        log = open("Automated logs/finish_transaction_script_disater.txt", "a")
        log.write("Error: "+ e +", "+str(datetime.datetime.now())+"\n")
        log.close()
    finally:
        if conn:
            conn.close()

check_show_7_close()
check_playing_shows()
check_pay_artist_ready()
