import os
import sys
import time
import random
import string
from string import Template
from bs4 import BeautifulSoup
from requests import get
import urllib.request
import urllib.parse
import pymysql
import hashlib #Used for password hashing
import datetime
import smtplib #Used for sending emails
import requests
from email.mime.multipart import MIMEMultipart #Used for sending emails
from email.mime.text import MIMEText #Used for sending emails
import stripe #Used for payment processing
import shutil
import json
import base64
import re
import bcrypt
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from requests.auth import HTTPBasicAuth
