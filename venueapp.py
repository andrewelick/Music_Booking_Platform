import os
import datetime
from flask import Flask
from flask import render_template
from flask import request
from flask import session
from flask import redirect
from flask import url_for
from flask import escape
from flask import Response
from flask import flash
from werkzeug import secure_filename
import venuehandler
import urllib.parse
import json
import base64
from dotenv import load_dotenv

#Load env variables
load_dotenv('test.env')

app = Flask(__name__, template_folder='Templates', static_folder='static')

#Cookies config
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax')

#Landing page, home page
@app.route("/", methods=["POST","GET"])
def index():
    #Account logged in
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #Check account
        account_type = venuehandler.check_account_type(email)

        if request.method == "POST":

            #Check if there is a stripe account setup
            if request.form.get("check_stripe_account"):
                return venuehandler.check_stripe_account(email)

            #Check if there is a payment method attached to the Stripe account
            if request.form.get("check_stripe_payment_method"):
                return venuehandler.check_stripe_payment_method(email, account_type)

        else:
            #Artist account
            if account_type == "artist":
                #Get showcase of venues
                venue_showcase = venuehandler.get_showcase_venues()

                #Get profile details
                profile_details = venuehandler.get_artist_profile_details(email)

                return render_template(
                    "artistindex.html",
                    uid = uid,
                    profile_details = profile_details,
                    venue_showcase=venue_showcase,
                    AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
                )

            #Venue account
            if account_type == "venue":

                #Load Individual show postings
                venue_profile_details = venuehandler.get_venue_profile_details(email)

                #Load featured artists
                featured_artists = venuehandler.get_featured_artists()

                return render_template("venueindex.html",
                    uid=uid,
                    venue_details=venue_profile_details,
                    featured_artists=featured_artists,
                    AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
                )

    else:

        #Load random artist uids for artist showcase
        if request.form.get("get_random_accounts"):
            return venuehandler.get_featured_artists(api = "yes", limit = 1)

        return render_template(
            'index.html',
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
        )

#Login page
@app.route("/login", methods=['GET','POST'])
def login_account():
    if request.method == 'POST':
        email = request.form['login_email']
        password = request.form['login_password']

        login_success = venuehandler.login_account(email,password)

        if login_success:
            session['username'] = email
            return "/"
        else:
            return "Incorrect email/password combination"
    else:
        if 'username' in session:
            return redirect(url_for('index'))
        else:
            return render_template('login.html')

#Logout of account
@app.route('/logout')
def account_logout():
    if 'username' in session:
        session.clear()

    return redirect(url_for('index'))

#Forgot password page
@app.route("/forgot", methods=['POST','GET'])
def forgot_password():

    if request.method == 'POST':
        reset_email = request.form['reset_email']
        return venuehandler.send_reset_password(reset_email)
    else:
        return render_template('forgotpassword.html')

#Change password page
@app.route("/changepassword", methods=['POST','GET'])
def change_password():
    if request.method == 'POST':
        uid = request.form['uid']
        reset_code = request.form['reset_code']
        password = request.form['change_password']
        confirm_password = request.form['change_confirm_password']

        if password == confirm_password:
            password_change_results = venuehandler.change_password(uid,reset_code,password)
            if password_change_results is True:
                return render_template("changepassword.html", change_password_results="True")
            else:
                return render_template("changepassword.html", change_password_results="Could not update password")
        else:
            return render_template("changepassword.html", change_password_results="Passwords do not match")
    else:
        uid = request.args.get('uid')
        reset_code = request.args.get('reset_code')
        return render_template("changepassword.html", uid=uid, reset_code=reset_code)

#Create account API
@app.route("/newaccount", methods=['POST'])
def create_account():

    #If create new account
    if request.form.get('submit_new_user'):
        #Form details
        name = request.form['new_name']
        email = request.form['new_email']
        password = request.form['new_password']
        confirm_password = request.form['new_confirm_password']
        account_type = request.form['new_account_type']

        account_result = venuehandler.create_new_account(email,password,confirm_password,name,account_type)

        #format json
        account_result_loaded = json.loads(account_result)

        if account_result_loaded['success']:
            session['username'] = email
            return account_result
        else:
            return account_result

#Check if email is being used
@app.route("/check_email_used", methods=['POST'])
def check_email_used():
    if request.method == "POST":
        #Email to be checked
        email = request.form['check_email_used']

        result = venuehandler.check_email_used(email)

        return result

#Set up account page
@app.route('/setupaccount', methods=['POST','GET'])
def setup_account():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #Get account type
        account_type = venuehandler.check_account_type(email)

        #If account save from artist
        if request.method == 'POST':

            #Picture upload
            if request.files.get('picture'):
                picture_data = request.files['picture']

                #Sanatize picture and save
                dir = "static/user_pictures/profile_pictures/"
                filename = uid+'_profile.jpg'

                #Save picture locally
                picture_data.save(os.path.join(dir, filename))

                #Save picture to AWS
                venuehandler.send_profile_picture_to_aws(uid)

                return json.dumps({'result': 'success'})

            if account_type == "artist":

                genre = request.form['genre']
                member = request.form['member_total']
                bio = request.form['bio']

                create_artist_profile = venuehandler.artist_profile_setup(email, genre, member, bio)

                if create_artist_profile:
                    return redirect(url_for('setup_connect_links'))
                else:
                    return render_template(
                        'setupaccount.html',
                        uid = uid,
                        AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
                    )

            #If account type is venue
            else:
                business_name = request.form['business_name']
                business_type = request.form['business_type']
                location = request.form['location']
                bio = request.form['bio']

                create_venue_profile = venuehandler.venue_profile_setup(email,business_name,business_type,location,bio)

                if create_venue_profile:
                    return redirect(url_for('setup_connect_links'))
        else:

            #Get method show page
            if account_type == "artist":
                page_url = "artistsetupaccount.html"
            else:
                page_url = "venuesetupaccount.html"

            return render_template(
                page_url,
                uid = uid,
                AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
            )
    else:
        return redirect(url_for('index'))

#Set up links page
@app.route("/setuplinks", methods=["POST","GET"])
def setup_connect_links():
    if 'username' in session:
        email= session['username']

        #Get account type
        account_type = venuehandler.check_account_type(email)

        #Artist account
        if account_type == 'artist':
            #Update Spotify user auth token
            if request.args.get("code"):
                user_spotify_auth = request.args.get("code")
                saved_spotify_token = venuehandler.set_spotify_access_token(email, user_spotify_auth)

            #Check if user has connected Spotify
            spotify_connected = venuehandler.get_spotify_access_token(email)

            #Save profile links
            if request.method == "POST":
                spotify_link = request.form['spotify_link']
                #bandcamp_link = request.form['bandcamp']
                bandcamp_link = None
                twitter_link = request.form['twitter']
                #instagram_link = request.form['instagram']
                instagram_link = None
                facebook_link = request.form['facebook']

                links_submitted = venuehandler.save_artist_profile_links(email,spotify_link,bandcamp_link,twitter_link,instagram_link,facebook_link)

                if links_submitted:
                    return redirect(url_for("add_payment_page"))
                else:
                    error = "Could not save information, please try again"
                    return render_template("setupartistlinks.html",spotify_connected=spotify_connected,error=error)
            else:
                return render_template('setupartistlinks.html', spotify_connected=spotify_connected)

        #Venue account
        if account_type == 'venue':

            if request.method == "POST":
                personal_website = request.form['personal_website']
                twitter = request.form['twitter']
                instagram = request.form['instagram']
                facebook = request.form['facebook']

                if personal_website == "":
                    personal_website = None
                if twitter == "":
                    twitter = None
                if instagram == "":
                    instagram = None
                if facebook == "":
                    facebook = None

                links_submitted = venuehandler.save_venue_profile_links(email,twitter,instagram,facebook,personal_website)

                if links_submitted:
                    return redirect(url_for("add_payment_page"))
                else:
                    error = "Could not save information, please try again"
                    return render_template("setupvenuelinks.html",error=error)
            else:
                return render_template("setupvenuelinks.html")
    else:
        return redirect(url_for('index'))

#Add payments page
@app.route("/addpayments", methods=["POST","GET"])
def add_payment_page():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        #Get account type
        account_type = venuehandler.check_account_type(email)

        #If ajax call
        if request.method == "POST":

            #If account is artist
            if account_type == "artist":
                #Dict of all the account details
                account_details = {
                    "firstName": request.form['firstName'],
                    "lastName": request.form['lastName'],
                    "birthday": request.form["Birthday"],
                    "SSN": request.form['SSN_num'],
                    "tos_acceptance": request.form['TOS_checkbox']
                }
            else:
                #If account is a venue

                #Dict of all the account details
                account_details = {
                    "businessName": request.form['businessName'],
                    "paymentName": request.form["paymentName"],
                }

            #Payment token from Stripe.js
            payment_token = request.form["payment_token"]
            account_details['payment_token'] = payment_token

            #Ip address of client
            ip_address = request.environ['REMOTE_ADDR']
            account_details['ip_address'] = ip_address

            #Save Account to Stripe
            account_result = venuehandler.create_stripe_account(email, account_type, account_details)

            return account_result
        else:
            #If account is an artist account
            if account_type == "artist":
                return render_template(
                    "paymentsetupartist.html",
                    account_type=account_type,
                    STRIPE_API_PUBLIC_KEY = os.getenv('STRIPE_API_PUBLIC_KEY'),
                )
            else:
                return render_template(
                    "paymentsetupvenue.html",
                    account_type=account_type,
                    STRIPE_API_PUBLIC_KEY = os.getenv('STRIPE_API_PUBLIC_KEY'),
                )
    else:
        return redirect(url_for("index"))

#Profile page
@app.route("/profile", methods=["POST","GET"])
def profile_page():
    if 'username' in session:
        uid = venuehandler.get_uid(session['username'])

        #Check if user account or someone else's
        if request.args.get("uid"):
            uid = request.args.get("uid")
            email = venuehandler.get_email(uid)

            #Redirect if users account
            if email == session['username']:
                return redirect(url_for("profile_page"))
        else:
            email = session['username']

        #If user sends message
        if request.method == "POST":
            rec_id = request.form["rec_id"]
            message = request.form["send_message"]

            send_new_message = venuehandler.create_new_message(session['username'],rec_id,message)

            if send_new_message:
                return redirect(url_for("profile_page", uid=rec_id))
            else:
                flash("Could not send message")

        #Check account type
        account_type = venuehandler.check_account_type(email)

        if account_type == 'artist':
            artist_details = venuehandler.get_artist_profile_details(email)
            artist_links = venuehandler.get_artist_links(email)

            return render_template(
                "artistprofile.html",
                email= email,
                uid = uid,
                artist_details= artist_details,
                artist_links= artist_links,
                AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
            )

        if account_type == 'venue':
            venue_details = venuehandler.get_venue_profile_details(email)
            venue_links = venuehandler.get_venue_links(email)

            return render_template(
                "venueprofile.html",
                email= email,
                uid= uid,
                venue_details= venue_details,
                venue_links= venue_links,
                AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
            )
    else:
        return "Please login to see this page"

#Individual show listed page
@app.route("/shows", methods=["POST","GET"])
def one_show_page():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        #Get show posting amd other information
        if request.args.get("id"):
            show_id = request.args.get("id")
            show_details = venuehandler.get_venue_one_show(show_id)

            #If coming from notification mark as read
            if request.args.get("noti"):
                venuehandler.mark_notification_read(show_id)

        return render_template(
            "showlisting.html",
            account_type=account_type,
            uid=uid,
            show_details=show_details,
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
        )
    else:
        return redirect(url_for("index"))


#Messages page
@app.route("/messages", methods=['POST','GET'])
def message_page():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #If thread is open
        if request.args.get("tid"):
            thread_id = request.args.get("tid")
            rec_id = request.args.get("rec_id")
            send_id = request.args.get("send_id")

            if request.args.get("count"):
                count= int(request.args.get("count")) + 15
                all_thread_messages = venuehandler.get_messages_one_thread(thread_id, count=count)
            else:
                all_thread_messages = venuehandler.get_messages_one_thread(thread_id)
                count= 10

            #Get other account details
            if rec_id != uid:
                thread_other_user = venuehandler.get_thread_other_user(rec_id)
            else:
                thread_other_user = venuehandler.get_thread_other_user(send_id)

            #Delete message notifications
            venuehandler.delete_message_notification(email,rec_id)

            return render_template(
                "messages.html",
                uid=uid,
                all_thread_messages=all_thread_messages,
                thread_id=thread_id,
                rec_id=rec_id,
                thread_other_user=thread_other_user,
                count=count,
                AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
            )

        #If user sends message in thread
        if request.method == "POST":
            rec_id = request.form['rec_id']
            new_message = request.form['new_message']
            thread_id = request.form['thread_id']
            noti_type = 1

            #Send message
            send_new_message = venuehandler.create_new_message(email,rec_id,new_message)

            #If message is sent redirect back to page
            if send_new_message:
                #Create notification
                venuehandler.create_new_notification(uid,rec_id,noti_type)

                return redirect(url_for(
                        "message_page",
                        tid=thread_id,
                        rec_id=rec_id
                    )
                )
            else:
                flash("Could not send message, please try again")
                return redirect(url_for(
                        "message_page",
                        tid=thread_id,
                        rec_id=rec_id
                    )
                )

        #Load all threads for user
        all_threads = venuehandler.get_messages_threads(email)

        return render_template("messages.html",
            uid=uid,
            all_threads=all_threads,
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
        )

#Notifications page
@app.route("/notifications")
def notifications_page():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        all_notis = venuehandler.get_all_notifications(uid)

        print(all_notis)
        return render_template(
            "notifications.html",
            all_notis=all_notis,
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
        )
    else:
        return redirect(url_for("index"))

#All user bids
@app.route("/upcomingshows")
def your_bids():
    if 'username' in session:
        email = session['username']

        return render_template(
            "upcomingshows.html",
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
        )
    else:
        return redirect(url_for("index"))

@app.route("/yourlistings")
def your_listings():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        return render_template(
            "yourlistings.html",
            uid=uid,
            AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME')
        )

    else:
        return redirect(url_for("/"))

#Payments dashboard
@app.route("/payments", methods=['POST','GET'])
def payments_dashboard():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        if request.method == "POST":

            #Check if there is a stripe account setup
            if request.form.get("check_stripe_account"):
                return venuehandler.check_stripe_account(email)

            #Stripe balance check
            if request.form.get("balance_check"):
                return venuehandler.get_stripe_account_balance(uid)

            #Stripe Payments check if has any
            if request.form.get("payment_methods"):
                return venuehandler.get_stripe_payment_methods(uid, account_type)

            #Get Stripe charges
            if request.form.get("get_charges"):
                starting_after = request.form.get("starting_after")
                return venuehandler.get_stripe_charges(uid, starting_after)

            if request.form.get("get_payments"):
                starting_after = request.form.get("starting_after")
                return venuehandler.get_stripe_payment_transactions(uid, starting_after)

            #Stripe payout transactions
            if request.form.get("get_cashout_transactions"):
                starting_after = request.form.get("starting_after")
                return venuehandler.get_stripe_payouts(uid, starting_after)

            #Add new payment method
            if request.form.get("new_payment"):
                payment_token = request.form.get("payment_token")
                return venuehandler.create_stripe_payment_method(email, account_type, payment_token)

            #Verify bank account
            if request.form.get("verify_bank_account"):
                bank_id = request.form.get("bank_id")
                micro_amount1 = request.form.get("micro_amount1")
                micro_amount2 = request.form.get("micro_amount2")
                return venuehandler.verify_bank_payment_method(email, bank_id, micro_amount1, micro_amount2)

            #Delete card
            if request.form.get("delete_payment"):
                payment_id = request.form.get('payment_id')
                return venuehandler.delete_stripe_payment_method(email, account_type, payment_id)

            #Send cashout request
            if request.form.get("send_cashout"):
                cashout_method = request.form.get('cashout_method')
                return venuehandler.create_stripe_payout_artist(uid, cashout_method)

        #Artist account
        if account_type == "artist":
            return render_template(
                "artistpaymentdashboard.html",
                STRIPE_API_PUBLIC_KEY = os.getenv('STRIPE_API_PUBLIC_KEY'),
            )
        else:
            #If account is venue
            return render_template(
                "venuepaymentdashboard.html",
                STRIPE_API_PUBLIC_KEY = os.getenv('STRIPE_API_PUBLIC_KEY'),
            )
    else:
        return redirect(url_for("index"))
#Edit profile page
@app.route("/editprofile", methods=["POST","GET"])
def edit_profile_page():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        #Save profile links and information
        if request.method == "POST":

            if account_type == "artist":

                if request.form.get('update_artist_profile'):
                    genre = request.form['genre']
                    member = request.form['member_total']
                    bio = request.form['bio']

                    #Change profile information
                    return venuehandler.artist_profile_setup(email,genre,member,bio)

                if request.form.get('update_artist_links'):
                    spotify_link = request.form['spotify_link']
                    #bandcamp_link = request.form['bandcamp']
                    bandcamp_link = None
                    twitter_link = request.form['twitter']
                    #instagram_link = request.form['instagram']
                    instagram_link = None
                    facebook_link = request.form['facebook']

                    #Change profile links
                    return venuehandler.save_artist_profile_links(email,spotify_link,bandcamp_link,twitter_link,instagram_link,facebook_link)
            else:

                if request.form.get('update_venue_profile'):
                    #Profile information
                    business_name = request.form['business_name']
                    business_type = request.form['business_type']
                    location = request.form['business_location']
                    bio = request.form['bio']

                    return venuehandler.venue_profile_setup(email,business_name,business_type,location,bio)

                if request.form.get('update_venue_links'):
                    #Links
                    personal_website = request.form['personal_website']
                    twitter = request.form['twitter']
                    instagram = request.form['instagram']
                    facebook = request.form['facebook']

                    if personal_website == "":
                        personal_website = None
                    if twitter == "":
                        twitter = None
                    if instagram == "":
                        instagram = None
                    if facebook == "":
                        facebook = None

                    return venuehandler.save_venue_profile_links(email,twitter,instagram,facebook,personal_website)
        else:
            #if account is an artist
            if account_type == "artist":
                profile_details = venuehandler.get_artist_profile_details(email)
                profile_links = venuehandler.get_artist_links(email)

                return render_template(
                    "editartistprofile.html",
                    uid=uid,
                    profile_details=profile_details,
                    profile_links=profile_links,
                    AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
                )

            else:
                venue_details = venuehandler.get_venue_profile_details(email)
                venue_links = venuehandler.get_venue_links(email)

                return render_template(
                    "editvenueprofile.html",
                    uid = uid,
                    venue_details=venue_details,
                    venue_links=venue_links,
                    AWS_BUCKET_NAME = os.getenv('AWS_BUCKET_NAME'),
                )
    else:
        return redirect(url_for("index"))

#Contact page
@app.route('/contact')
def contact_us():
    return render_template('contactus.html')

#Terms and Conditions
@app.route('/terms')
def terms_conditions():
    return render_template("terms.html")

#Privacy
@app.route('/privacy')
def privacy():
    return render_template("privacy.html")

#Get AWS profile picture
@app.route('/profilepicture', methods=["POST"])
def get_profile_picture():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        return venuehandler.get_profile_picture_url(uid, ajax_request = "yes")

#Header, loads all info needed
@app.context_processor
def load_header_vars():
    if 'username' in session:
        header_email = session['username']
        account_type = venuehandler.check_account_type(header_email)
        noti_number = venuehandler.get_notification_number(header_email)

        return dict(header_email=header_email,account_type=account_type,noti_number=noti_number)
    else:
        return dict(header_email=None,account_type=None,noti_number=None)

##--- Artist bids API CALLS --------
@app.route('/artist_bids', methods=['POST'])
def artist_bids():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        #Check if winning bid
        if request.form.get('check_show_for_winner'):
            show_id = request.form.get('show_id')
            return venuehandler.check_winning_bid(show_id)

        #Get artist bids for one show
        if request.form.get('get_single_show_bids'):
            show_id = request.form.get('show_id')
            return venuehandler.get_full_bid_info(show_id)

        #Get all artist shows that they have one and will be performing
        if request.form.get('get_upcoming_artist_shows'):
            return venuehandler.get_upcoming_artist_shows(uid)

        #Get all bids for one artist
        if request.form.get('get_all_artist_bids'):
            return venuehandler.get_all_artist_bids(uid)

        #Place new bid
        if request.form.get('place_bid'):
            new_bid_price = request.form['new_bid_price']
            show_id = request.form['show_id']
            return venuehandler.place_bid_on_show(uid,show_id,new_bid_price)

        #Delete artist bid
        if request.form.get('delete_artist_bid'):
            bid_id = request.form.get('bid_id')
            return venuehandler.delete_bid(bid_id, uid)

        #Accept bid offer
        if request.form.get('accept_bid_offer'):
            bid_id = request.form.get('bid_id')

            #Save transaction into our database, will charge using stripe at later date
            return venuehandler.accept_bid_offer(bid_id)

    else:
        return json.dumps({'error': 'Must be logged in'})

###----Show posting API calls -----------------
#New show posting
@app.route('/newshow', methods=['POST'])
def post_new_show():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        if account_type == 'venue':

            if request.form.get('new_show'):
                #All show inputs
                show_inputs = request.form.get('show_inputs')
                return venuehandler.create_show_posting(uid, show_inputs)

        else:
            result = "Must be venue account"
    else:
        return json.dumps({'error': 'must be logged in'})

#Show postings endpoint
@app.route('/show_postings', methods=['POST'])
def show_posting_endpoint():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)
        account_type = venuehandler.check_account_type(email)

        #Get all show postings
        if request.form.get('get_all_postings'):
            return venuehandler.get_venue_show_postings()

        #Get specific user's show postings
        elif request.form.get('get_user_postings'):
            venue_id = request.form.get('venue_id')
            return venuehandler.get_venue_show_postings(uid = venue_id)

        #Get specific user's show postings that are ending in 2 weeks
        elif request.form.get('get_user_postings_ending_soon'):
            venue_id = request.form.get('venue_id')
            return venuehandler.get_venue_show_postings(uid = venue_id, ending_soon = True)
    else:

        #Random postings for homepage
        if request.form.get('get_random_postings'):
            limit = request.form.get('limit')
            return venuehandler.get_venue_show_postings(limit = limit)
        else:
            json.dumps({'error': 'Must be logged in'})

###--Artist media API CALLS---------------
@app.route('/artist_media', methods=['POST', 'GET'])
def artist_media():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        if request.method == "POST":

            #Save new media
            if request.form.get("save_media"):
                #Save artist media
                type = request.form['type']
                src = request.form['src']

                return venuehandler.create_artist_media(uid, type, src)

            #Load artist media
            if request.form.get("load_media"):
                artist_id = request.form['artist_id']

                #If profile is the current user
                if artist_id == "load_current_user":
                    artist_id = uid

                return venuehandler.get_artist_media(artist_id)

            #Delete artist media
            if request.form.get("delete_media"):
                media_id = request.form["media_id"]

                return venuehandler.delete_artist_media(uid, media_id)

#--- Spotify API section ---------------------------------

#Connect user Spotify account
@app.route('/connectspotify')
def connect_spotify():
    scopes = ""
    client_id = "c74d1fc0c128497b8e42890d5fc900bf"
    uri = urllib.parse.quote_plus("https://www.blufftour.com/setuplinks")
    return redirect("https://accounts.spotify.com/authorize?client_id="+client_id+"&response_type=code&redirect_uri="+uri)

@app.route('/spotify_resources', methods=['POST'])
def spotify_resources():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #If user has linked spotify account
        check_spotify_token = venuehandler.check_spotify_access_token(email)

        if check_spotify_token:

            #Get Spotify top tracks
            if request.form.get("get_top_tracks"):
                return venuehandler.get_spotify_top_tracks(email)

            #Get Spotify albums
            if request.form.get("get_albums"):
                return venuehandler.get_spotify_albums(email)

            #Get Spotify followers count
            if request.form.get("get_followers"):
                return venuehandler.get_spotify_follower_count(email)
        else:
            return json.dumps({"error": "no spotify account"})



#--- Random testing endpoint --#--------#--------#-------#--------#---------

@app.route('/playground', methods=['GET'])
def playground():
    return render_template('email_files/resetpassword.html')


#--- 404 error page -------------------------------------------
@app.errorhandler(404)
# inbuilt function which takes error as parameter
def not_found(e):
    return render_template("404.html")

app.secret_key = "Jesus Di3d 4or Your Zins"

if __name__ == '__main__':
    app.run(port = os.getenv('PORT'), debug= os.getenv('DEBUG'))
