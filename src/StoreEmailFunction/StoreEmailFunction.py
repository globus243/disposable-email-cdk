import mimetypes
import uuid
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
import json
import os
import logging
import re
from email import encoders, message_from_string
from email import policy

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

ses = boto3.client( 'ses', region_name = "eu-west-1" )
s3 = boto3.resource( 's3' )
dynamodb = boto3.resource( "dynamodb" )

emails_table = dynamodb.Table( os.environ[ 'emails_table_name' ] )
addresses_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )
reply_addresses_table = dynamodb.Table( os.environ[ 'reply_addresses_table_name' ] )

valid_domains = os.environ[ 'valid_domains' ].split( ',' )
bucket_name = os.environ[ 'emails_bucket_name' ]


def store_email( email ):
    """
    Stores email information in DynamoDB
    :param  email: email object
    :raises ClientError: DynamoDB Client Exception
    """
    try:
        emails_table.put_item(
                Item = {
                    'destination':   email[ 'destination' ][ 0 ],
                    'messageId':     email[ 'messageId' ],
                    'timestamp':     email[ 'timestamp' ],
                    'source':        email[ 'source' ],
                    'commonHeaders': email[ 'commonHeaders' ],
                    'isNew':         True
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )


def check_redirect_exists( actual_address, disposable_address ):
    """
    Checks and returns if there is a proxy_address for a given disposable_address and recipient
    For each person a disposable address is communicating with there is a unique proxy address
    :param  actual_address: the address of the external person the redirect is for
    :param  disposable_address: the disposable address the redirect is for
    :return: the proxy address if it exists, None otherwise
    :raises ClientError: DynamoDB Client Exception
    """
    try:
        response = reply_addresses_table.scan(
                FilterExpression = Attr( 'actualAddress' ).eq( actual_address )
                                   & Attr( 'disposableAddress' ).eq( disposable_address )
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Items' in response:
            if len( response[ 'Items' ] ) > 0:
                return response[ 'Items' ][ 0 ]
    return None


def generate_email( original_address ):
    """
    Generates a unique email address for a given name
    E.g.: peter -> 12345678-1234-1234-1234-123456789012+peter@valid_domain.com
    :param original_address: the original email address (the part before the @)
    :return: the generated email address
    """
    return str( uuid.uuid4( ) ) + "+" + original_address + "@" + valid_domains[ 0 ]


def create_redirect( proxy_address, actual_address, disposable_address ):
    """
    Creates a redirect for a given proxy_address, actual_address and disposable_address
    :param proxy_address: the new proxy address emails can be sent to
    :param actual_address: the address of the external person the redirect is for ( he will receive the emails send to the proxy address )
    :param disposable_address: the disposable address the redirect is for ( the address the external person will reply to )
    :raises ClientError: DynamoDB Client Exception
    """
    try:
        reply_addresses_table.put_item(
                Item = {
                    'proxyAddress':      proxy_address,
                    'actualAddress':     actual_address,
                    'disposableAddress': disposable_address
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )


def redirect_enabled( destination ):
    """
    Checks if the redirect is enabled for a given disposable address
    :param destination: the disposable address
    :return: [bool, string] - True if the redirect is enabled, False otherwise
    """
    try:
        response = addresses_table.get_item(
                Key = {
                    'address': destination
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Item' in response:
            item = response[ 'Item' ]
            return { 'enabled': item[ 'redirect' ], 'actualAddress': item[ 'redirect_email' ] }
    return None


def load_email_from_s3( message_id ):
    """
    Loads the raw email file from S3
    :param message_id: the message id of the email ( message id is the same as the object key in S3 )
    :return: Array with the html and text parts of the email
    """
    obj = s3.Object( bucket_name, message_id )
    body = obj.get( )[ 'Body' ].read( )
    msg = message_from_string( body.decode( 'utf-8' ), policy = policy.default )
    html_body = msg.get_body( 'html' ).get_content( )
    plain_body = msg.get_body( 'plain' ).get_content( )
    attachments = [ ]
    for part in msg.walk( ):
        if part.get_content_maintype( ) == 'multipart':
            continue
        if part.get( 'Content-Disposition' ) is None:
            continue
        filename = part.get_filename( )
        if not filename:
            ext = mimetypes.guess_extension( part.get_content_type( ) )
            if not ext:
                ext = '.bin'
            filename = 'part-%03d%s' % (len( attachments ), ext)
        attachments.append(
                {
                    'filename': filename,
                    'content':  part.get_payload( decode = True )
                } )
    return html_body, plain_body, attachments


def extract_email( email ):
    """
    Extracts the email address from a string

    :param email: the string to extract the email address from
    :return: the extracted email address
    """
    return re.search( r'[\w.-]+@[\w.-]+', email ).group( 0 )


def proxy_address_exists( proxy_address ):
    """
    Checks if a proxy address exists and return the item if it does

    :param proxy_address: the proxy address to check
    :return: the item if it exists, None otherwise
    """
    try:
        response = reply_addresses_table.get_item(
                Key = {
                    'proxyAddress': proxy_address
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Item' in response:
            return response[ 'Item' ]
    return None


def contains_uuid( string ):
    """
    Checks if a string contains an uuid

    :param string: the string to check
    :return: True if the string contains an uuid, False otherwise
    """
    return re.match( r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', string )


def lambda_handler( event, context ):
    logger.info( '## ENVIRONMENT VARIABLES' )
    logger.info( os.environ )
    logger.info( '## EVENT' )
    logger.info( event )

    mail = json.loads( event[ 'Records' ][ 0 ][ 'Sns' ][ 'Message' ] )[ 'mail' ]
    source = extract_email( mail[ 'commonHeaders' ][ 'from' ][ 0 ] )
    destination = mail[ 'destination' ][ 0 ]

    to_address = None
    from_address = None

    is_redirected_email = False
    disposable_email_item = None
    # non-expensive check if email was send to proxy- or disposable address, possibly saving 1 DynamoDB call
    if not contains_uuid( destination ):
        disposable_email_item = redirect_enabled( destination )
    if disposable_email_item is not None:  # email send to disposable address
        if disposable_email_item[ 'enabled' ]:
            redirect = check_redirect_exists( source, destination )
            to_address = disposable_email_item[ 'actualAddress' ]
            if redirect is not None:
                from_address = redirect[ 'proxyAddress' ]
            else:
                proxy_address = generate_email( source.split( '@' )[ 0 ] )
                create_redirect( proxy_address, source, destination )
                from_address = proxy_address
        store_email( mail )
    else:  # proxy address
        redirect = proxy_address_exists( destination )
        if redirect is not None:  # if None, email was send to a non-existing proxy address
            to_address = redirect[ 'actualAddress' ]
            from_address = redirect[ 'disposableAddress' ]
        # delete redirected messages from S3
        is_redirected_email = True

    if to_address is not None and from_address is not None:
        [ html_body, plain_body, attachments ] = load_email_from_s3( mail[ 'messageId' ] )
        msg = MIMEMultipart( 'mixed' )
        msg[ 'Subject' ] = mail[ 'commonHeaders' ][ 'subject' ]
        msg[ 'From' ] = from_address
        msg[ 'To' ] = to_address
        msg.preamble = 'This is a multi-part message in MIME format.'
        msg.attach( MIMEText( html_body, 'html' ) )
        for attachment in attachments:
            part = MIMEBase( 'application', "octet-stream" )
            part.set_payload( attachment[ 'content' ] )
            encoders.encode_base64( part )
            part.add_header( 'Content-Disposition', 'attachment; filename="%s"' % attachment[ 'filename' ] )
            msg.attach( part )

        ses.send_raw_email(
                Source = from_address,
                Destinations = [ to_address ],
                RawMessage = { 'Data': msg.as_string( ) }
        )

    if is_redirected_email:
        logger.info( "## delete Message from S3 with ID:" )
        logger.info( mail[ 'messageId' ] )
        s3.Object( bucket_name, mail[ 'messageId' ] ).delete( )
