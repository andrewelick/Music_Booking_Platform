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

            #Venue shows that are ending soon
            elif request.form.get('ending_shows'):
                return venuehandler.get_venue_show_postings_ending_soon(uid)
            else:
                #Details for new show post
                show_price = request.form['show_price']
                show_description = request.form['show_description']
                show_artist = request.form['show_artist']
                show_date = request.form['show_date']
                #Format show date
                show_split = show_date.split("/")
                show_month = show_split[0]
                show_day = show_split[1]
                show_year = show_split[2]
                #Show time
                show_hour = request.form['show_hour']
                show_min = request.form['show_min']
                am_pm = request.form['show_am_pm']
                show_date = datetime.datetime(int(show_year),int(show_month),int(show_day),int(show_hour),int(show_min),0)

                result = venuehandler.create_show_posting(email,show_price,show_description,show_artist,show_date,am_pm)

            if result:
                return redirect(url_for("index"))
            else:
                return render_template("venueindex.html", uid=uid, venue_show_postings=venue_show_postings, result=result)
        else:
            #Artist account
            if account_type == "artist":
                #Get show listings
                all_listings = venuehandler.get_all_show_listings()
                venue_showcase = venuehandler.get_showcase_venues()

                #Get profile details
                profile_details = venuehandler.get_artist_profile_details(email)

                #Get your bids
                open_bids = len(venuehandler.get_all_bids(email))

                #Get upcoming shows for artist
                upcoming_shows = len(venuehandler.get_upcoming_artist_shows(email))

                return render_template("artistindex.html", uid = uid, profile_details = profile_details, upcoming_shows = upcoming_shows, all_listings=all_listings, venue_showcase=venue_showcase, open_bids = open_bids)

            #Venue account
            if account_type == "venue":

                #Load Individual show postings
                venue_profile_details = venuehandler.get_venue_profile_details(email)

                #Load featured artists
                featured_artists = venuehandler.get_featured_artists()

                return render_template("venueindex.html", uid=uid, venue_details=venue_profile_details, featured_artists=featured_artists)
    else:

        #Load random artist uids for artist showcase
        if request.form.get("get_random_accounts"):
            return venuehandler.get_random_accounts_uid()

        return render_template('index.html')

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
        return render_template('index.html')
    else:
        return render_template('index.html')

#Forgot password page
@app.route("/forgot", methods=['POST','GET'])
def forgot_password():

    if request.method == 'POST':
        reset_email = request.form['reset_email']
        recover_results = venuehandler.send_reset_password(reset_email)

        if recover_results is True:
            recover_results = "An email has been sent to your address"
            return render_template("forgotpassword.html", recover_results=recover_results)
        elif recover_results == "unused":
            recover_results = "No account associated with that email address"
            return render_template("forgotpassword.html", recover_results=recover_results)
        else:
            recover_results = "Unable to send password request"
            return render_template("forgotpassword.html", recover_results=recover_results)
    else:
        return render_template('forgotpassword.html', recover_results="")

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

#Create account page
@app.route("/newaccount", methods=['POST'])
def create_account():
    #If create new account
    if request.method == 'POST':
        #Form details
        name = request.form['new_name']
        email = request.form['new_email']
        password = request.form['new_password']
        confirm_password = request.form['new_confirm_password']
        account_type = request.form['new_account_type']

        account_result = venuehandler.create_new_account(email,password,confirm_password,name,account_type)

        if account_result is True:
            session['username'] = email
            return redirect(url_for("setup_account"))
        else:
            error = account_result
            return render_template('createaccount.html', account_result=error)

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
        if request.method == 'POST' and account_type == "artist":

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

            else:

                genre = request.form['genre']
                member = request.form['member_total']
                bio = request.form['bio']

                create_artist_profile = venuehandler.artist_profile_setup(email,genre,member,bio)

                if create_artist_profile:
                    return redirect(url_for('setup_connect_links'))
                else:
                    return render_template('setupaccount.html', uid = uid)

        #Save venue profile
        elif request.method == 'POST' and account_type == "venue":

            #Picture upload
            if request.files.get('picture'):
                picture_data = request.files['picture']

                #Sanatize picture and save
                dir = "static/user_pictures/profile_pictures/"
                filename = uid+'_profile.jpg'

                picture_data.save(os.path.join(dir, filename))

                return json.dumps({'result': 'success'})
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
                return render_template("artistsetupaccount.html", uid = uid)
            else:
                return render_template("venuesetupaccount.html", uid = uid)
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
                youtube_link = request.form['youtube']
                soundcloud_link = request.form['soundcloud']
                bandcamp_link = request.form['bandcamp']
                twitter_link = request.form['twitter']
                instagram_link = request.form['instagram']
                facebook_link = request.form['facebook']

                links_submitted = venuehandler.save_artist_profile_links(email,youtube_link,soundcloud_link,bandcamp_link,twitter_link,instagram_link,facebook_link)

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
                return render_template("paymentsetupartist.html", account_type=account_type)
            else:
                return render_template("paymentsetupvenue.html", account_type=account_type)
    else:
        return redirect(url_for("index"))

#Profile page
@app.route("/profile", methods=["POST","GET"])
def profile_page():
    if 'username' in session:

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

            #If user has linked spotify account
            check_spotify_token = venuehandler.check_spotify_access_token(email)

            if check_spotify_token:
                spotify_top_tracks = venuehandler.get_spotify_top_tracks(email)
                spotify_albums = venuehandler.get_spotify_albums(email)
                spotify_follow_uri = venuehandler.get_spotify_account_uri(email)

                return render_template("artistprofile.html", email=email, artist_details=artist_details, artist_links=artist_links,spotify_albums=spotify_albums,spotify_top_tracks=spotify_top_tracks, spotify_follow_uri=spotify_follow_uri)
            else:
                return render_template("artistprofile.html", email=email, artist_details=artist_details,artist_links=artist_links)

        if account_type == 'venue':
            uid = venuehandler.get_uid(email)
            venue_details = venuehandler.get_venue_profile_details(email)
            venue_links = venuehandler.get_venue_links(email)

            #Get all of the users shows
            your_show_listings = venuehandler.get_all_your_listings(email)

            #Lists for the active/nonactive shows
            winning_show = []
            active_show = []

            #Loop through all shows and filter them
            for x in your_show_listings:
                if 'winner' in x:
                    winning_show.append(x)
                else:
                    active_show.append(x)

            return render_template("venueprofile.html", email=email, uid=uid, venue_details=venue_details,venue_links=venue_links, winning_show=winning_show, active_show= active_show)
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
            venue_details = venuehandler.get_listing_profile_details(show_details[1])

            #Check if winning bid
            winning_bid = venuehandler.check_winning_bid(show_id)

            #If there is no winner
            if winning_bid == False:
                bids_info = venuehandler.get_full_bid_info(show_id)
                bids_stats = venuehandler.get_bids_stats(show_id)
            else:
                bids_info = None
                bids_stats = None

            #If coming from notification mark as read
            if request.args.get("noti"):
                venuehandler.mark_notification_read(show_id)

        #If post action
        if request.method == "POST":

            #Accept bid offer
            if request.form.get("acceptoffer"):
                artist_uid = request.form["winning_bidder_uid"]
                venue_uid = uid

                #Save transaction into our database, will charge using stripe at later date
                change_bid_winner = venuehandler.accept_bid_offer(show_id,artist_uid,venue_uid)

                #If transaction was completed
                if change_bid_winner is not False:

                    #Send notification to winner of bid
                    process_winner_notification = venuehandler.create_new_notification(email,artist_uid,3,show_id=show_id)

                    if process_winner_notification:
                        return redirect(url_for("index"))
                    else:
                        return redirect(url_for("profile_page"))

            #Delete a bid
            elif request.form.get('deletebid'):
                bid_deleted = venuehandler.delete_bid(email,show_id)

                if bid_deleted:
                    return redirect(url_for("one_show_page", id=show_id))
                else:
                    return redirect(url_for("profile_page"))
            else:
                #Create new bid
                new_bid_price = request.form['new_bid_price']
                place_bid = venuehandler.place_bid_on_show(email,show_id,new_bid_price)

                if place_bid:
                    #If use has already bid on show
                    if place_bid == "already_bid":
                        flash("You have already bid on this show")
                    else:
                        #Send notification
                        send_id = email
                        rec_id = show_details[1]
                        noti_type = 2
                        venuehandler.create_new_notification(send_id,rec_id,noti_type,show_id=show_id)

                        return redirect(url_for("one_show_page", id=show_id))
                else:
                    return "Could not place bid"

        return render_template("showlisting.html", account_type=account_type, uid=uid, show_details=show_details,venue_details=venue_details,bids_info=bids_info,bids_stats=bids_stats, winning_bid=winning_bid)
    else:
        return redirect(url_for("index"))

    #Delete bid from show
    def delete_bid():
        if request.method == "POST":
            email = session["username"]
            show_id = request.form["show_id"]

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

            if request.args.get("count"):
                count= int(request.args.get("count")) + 15
                all_thread_messages = venuehandler.get_messages_one_thread(thread_id, count=count)
            else:
                all_thread_messages = venuehandler.get_messages_one_thread(thread_id)
                count= 10

            thread_other_user = venuehandler.get_thread_other_user(rec_id)

            #Delete message notifications
            venuehandler.delete_message_notification(email,rec_id)

            return render_template("messages.html", uid=uid, all_thread_messages=all_thread_messages, thread_id=thread_id, rec_id=rec_id, thread_other_user=thread_other_user,count=count)

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
                venuehandler.create_new_notification(email,rec_id,noti_type)

                return redirect(url_for("message_page", tid=thread_id,rec_id=rec_id))
            else:
                flash("Could not send message, please try again")
                return redirect(url_for("message_page", tid=thread_id, rec_id=rec_id))

        #Load all threads for user
        all_threads = venuehandler.get_messages_threads(email)
        return render_template("messages.html", uid=uid, all_threads=all_threads)

#Notifications page
@app.route("/notifications")
def notifications_page():
    if 'username' in session:
        email = session['username']
        all_notis = venuehandler.get_all_notifications(email)

        return render_template("notifications.html", all_notis=all_notis)
    else:
        return redirect(url_for("index"))

#All user bids
@app.route("/upcomingshows")
def your_bids():
    if 'username' in session:
        email = session['username']

        #Get your bids
        all_user_bids = venuehandler.get_all_bids(email)

        #Get upcoming shows for artist
        upcoming_shows = venuehandler.get_upcoming_artist_shows(email)

        return render_template("upcomingshows.html", all_user_bids=all_user_bids, upcoming_shows=upcoming_shows)
    else:
        return redirect(url_for("index"))

@app.route("/yourlistings")
def your_listings():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #Get all of the users shows
        your_show_listings = venuehandler.get_all_your_listings(email)
        venue_profile_details = venuehandler.get_venue_profile_details(email)

        #Lists for the active/nonactive shows
        winning_show = []
        active_show = []

        #Loop through all shows and filter them
        for x in your_show_listings:
            if 'winner' in x:
                winning_show.append(x)
            else:
                active_show.append(x)

        return render_template("yourlistings.html", uid=uid, venue_details=venue_profile_details, winning_show=winning_show, active_show= active_show)
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

            #Stripe Payments check
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
            return render_template("artistpaymentdashboard.html")
        else:
            #If account is venue
            return render_template("venuepaymentdashboard.html")
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
                genre = request.form['genre']
                member = request.form['member_total']
                bio = request.form['bio']
                #Change profile information
                changed_artist_profile = venuehandler.artist_profile_setup(email,genre,member,bio)

                youtube_link = request.form['youtube']
                soundcloud_link = request.form['soundcloud']
                bandcamp_link = request.form['bandcamp']
                twitter_link = request.form['twitter']
                instagram_link = request.form['instagram']
                facebook_link = request.form['facebook']
                #Change profile links
                links_submitted = venuehandler.save_artist_profile_links(email,youtube_link,soundcloud_link,bandcamp_link,twitter_link,instagram_link,facebook_link)

                if changed_artist_profile and links_submitted:
                    flash("Your changes were saved!")
                else:
                    flash("There was an error saving your information")

                return redirect(url_for("edit_profile_page"))
            else:
                #Profile information
                business_name = request.form['business_name']
                business_type = request.form['business_type']
                location = request.form['location']
                bio = request.form['bio']

                #Update profile picture
                if 'profile_picture_file' in request.files:
                    profile_picture_file = request.files['profile_picture_file']
                    filename = uid+'_profile.jpg'
                    profile_picture_file.save("static/user_pictures/profile_pictures/"+filename)


                changed_venue_profile = venuehandler.venue_profile_setup(email,business_name,business_type,location,bio)

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

                links_submitted = venuehandler.save_venue_profile_links(email,twitter,instagram,facebook,personal_website)

                if changed_venue_profile and links_submitted:
                    flash("Your changes where saved!")
                else:
                    flash("There was an error saving your information")

                return redirect(url_for("edit_profile_page"))
        else:
            #if account is an artist
            if account_type == "artist":
                profile_details = venuehandler.get_artist_profile_details(email)
                profile_links = venuehandler.get_artist_links(email)

                return render_template("editartistprofile.html", uid=uid, profile_details=profile_details, profile_links=profile_links)

            else:
                venue_details = venuehandler.get_venue_profile_details(email)
                venue_links = venuehandler.get_venue_links(email)

                return render_template("editvenueprofile.html", uid = uid, venue_details=venue_details,venue_links=venue_links)
    else:
        return redirect(url_for("index"))

#Contact page
@app.route('/contact')
def contact_us():
    if 'username' in session:
        return render_template('contactus.html')
    else:
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
#Get bidder details
@app.context_processor
def utility_processor():
    def get_bidder_details(uid):
        bidder_details = venuehandler.find_bidder_details(uid)
        return bidder_details
    return dict(bidder_details=get_bidder_details)

#Get show posting bid stats for venues
@app.context_processor
def utility_processor():
    def get_bids_for_show(show_id):
        bids = venuehandler.get_bids_stats(show_id)
        return bids
    return dict(show_bids_stats=get_bids_for_show)




#--- Spotify API section ---------------------------------

#Connect user Spotify account
@app.route('/connectspotify')
def connect_spotify():
    scopes = ""
    client_id = "c74d1fc0c128497b8e42890d5fc900bf"
    uri = urllib.parse.quote_plus("http://localhost/setuplinks")
    return redirect("https://accounts.spotify.com/authorize?client_id="+client_id+"&response_type=code&redirect_uri="+uri)

@app.route('/spotify_resources', methods=['POST'])
def spotify_resources():
    if 'username' in session:
        email = session['username']
        uid = venuehandler.get_uid(email)

        #Get Spotify followers count
        if request.form.get("get_followers"):
            return venuehandler.get_spotify_follower_count(email)

    else:
        return json.dumps()



#------#--------#--------#-------#--------#---------

app.secret_key = "Jesus Di3d 4or Your Zins"

app.run()
