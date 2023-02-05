import base64
import json
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import boto3
from botocore.exceptions import ClientError
import os
import logging
import time

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

ses = boto3.client( 'ses', region_name = "eu-west-1" )
dynamodb = boto3.resource( "dynamodb" )

address_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )
emails_table = dynamodb.Table( os.environ[ 'emails_table_name' ] )

cors_allowed_origins = os.environ[ 'cors_allowed_origins' ].split( ',' )
default_allowed_origin = cors_allowed_origins[ 0 ]


def address_exists_and_user_owned( address, username ):
    """
    Checks if the address exists and if the user owns it

    :param address: the disposable email address
    :param username: the username
    :return: True if the address exists and the user owns it, False otherwise
    :raises: ClientError: DynamoDB client exception
    """
    try:
        response = address_table.get_item(
                Key = {
                    'address': address
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Item' in response:
            item = response[ 'Item' ]
            if item[ 'ttl' ] > int( time.time( ) ) \
                    and item[ 'username' ] == username:
                return True
    return False


def user_owns_address( address, username ):
    """
    check if a given address belongs to a given user

    :param address: the disposable address to check
    :param username: the username to check against
    :return: True if the address belongs to the user, False otherwise
    :raises ClientError: DynamoDB Client Exception
    """
    try:
        response = address_table.get_item(
                Key = {
                    'address': address
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Item' in response:
            item = response[ 'Item' ]
            if item[ 'username' ] == username:
                return True
    return False


def get_allowed_origins( origin ):
    """
    Gets the allowed origins from the environment and checks if a given origin is allowed
    :param origin: the origin to check
    :return: origin if allowed, else default origin
    """
    if origin in cors_allowed_origins:
        return origin
    return default_allowed_origin


def lambda_handler( event, context ):
    logger.info( '## ENVIRONMENT VARIABLES' )
    logger.info( os.environ )
    logger.info( '## EVENT' )
    logger.info( event )

    origin = event.get( 'headers', { } ).get( 'origin', default_allowed_origin )
    username = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get(
        'cognito:username' )

    body = json.loads( event.get( 'body', { } ) )

    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "GET,OPTIONS,POST",
        "access-control-allow-origin":  get_allowed_origins( origin ),
        'Content-Type':                 'application/json'
    }

    to_addresses = body.get( 'toAddress' )
    from_address = body.get( 'fromAddress' )
    subject = body.get( 'subject' )
    email_html = body.get( 'emailBodyHtml' )
    email_text = body.get( 'emailBodyText' )
    attachments = body.get( 'attachments', [ ] )

    if None not in [ to_addresses, from_address, subject, email_html, email_text, username ]:
        if address_exists_and_user_owned( from_address, username ):
            try:
                msg = MIMEMultipart( 'mixed' )
                msg[ 'Subject' ] = subject
                msg[ 'From' ] = from_address
                msg[ 'To' ] = to_addresses[ 0 ]
                msg.preamble = 'This is a multi-part message in MIME format.'
                msg.attach( MIMEText( email_html, 'html' ) )
                for attachment in attachments:
                    part = MIMEBase( 'application', "octet-stream" )
                    part.set_payload( base64.b64decode( attachment[ 'content' ] ) )
                    encoders.encode_base64( part )
                    part.add_header( 'Content-Disposition', 'attachment; filename="%s"' % attachment[ 'name' ] )
                    msg.attach( part )

                ses.send_raw_email(
                        Source = from_address,
                        Destinations = to_addresses,
                        RawMessage = { 'Data': msg.as_string( ) }
                )
            except ClientError as e:
                logger.info( '## SES Client Exception' )
                logger.info( e.response[ 'Error' ][ 'Message' ] )
            else:
                return {
                    'statusCode': 200,
                    'body':       json.dumps( { 'message': 'Email sent successfully' } ),
                    'headers':    headers
                }

    return {
        'statusCode': 400,
        'body':       json.dumps( { 'message': 'missing or invalid parameters' } ),
        'headers':    headers
    }
