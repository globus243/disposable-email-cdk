import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError
import json
import os
import logging
import time
import re

from random_values import return_random_address

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

dynamodb = boto3.resource( "dynamodb" )
addresses_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )

valid_domains = os.environ[ 'valid_domains' ].split( ',' )
mailboxTTL = int( os.environ[ 'mailbox_ttl' ] )

cors_allowed_origins = os.environ[ 'cors_allowed_origins' ].split( ',' )
default_allowed_origin = cors_allowed_origins[ 0 ]


def address_exists( address ):
    """
    check if a given address exists
    :param address:
    :return:
    """
    try:
        response = addresses_table.get_item(
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
            if item[ 'ttl' ] > int( time.time( ) ):
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
        response = addresses_table.get_item(
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


def create_address( address, username, redirect_address ):
    """
    create a new disposable address
    :param address: the new disposable address
    :param username: the username to associate with the address
    :param redirect_address: the address to redirect to
    :raises ClientError: DynamoDB Client Exception
    """
    ttl = int( time.time( ) ) + mailboxTTL
    try:
        addresses_table.put_item(
                Item = {
                    'address':        address,
                    'ttl':            ttl,
                    'username':       username,
                    'redirect_email': redirect_address,
                    'redirect':       True
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )


def get_all_addresses( username ):
    """
    get all addresses for a given user
    :param username: the username to get addresses for
    :return: a list of addresses with TTLs, redirect addresses, and redirect flags
    """
    addresses = [ ]
    ttl = int( time.time( ) )
    try:
        response = addresses_table.scan(
                FilterExpression = Attr( 'username' ).eq( username ) & Attr( 'ttl' ).gt( ttl )
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        for item in response[ 'Items' ]:
            addresses.append(
                    {
                        'address':        item[ 'address' ],
                        'ttl':            str( item[ 'ttl' ] ),
                        "redirect":       item[ "redirect" ],
                        "redirect_email": item[ "redirect_email" ]
                    } )
    return addresses


def validate_email( address ):
    """
    check if a given email address is 1 valid and 2 in the list of valid domains
    :param address: the email address to validate
    :return: True if the email address is valid, False otherwise
    """
    if type( address ) is not str:
        return False
    if re.match( '^.+@(\\[?)[a-zA-Z0-9\\-.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(]?)$', address ) is not None:
        domain = address.split( '@' )[ 1 ]
        if domain in valid_domains:
            return True
    return False


def generate_unique_random_email( ):
    """
    generate a unique random email address
    :return: a unique random email address in the format lastname.firstname.99@valid_domain
    """
    email_address = return_random_address( ) + '@' + valid_domains[ 0 ]
    while address_exists( email_address ):
        email_address = return_random_address( ) + '@' + valid_domains[ 0 ]
    return email_address


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
    logger.info( '## Configuration' )
    logger.info( 'Domains: {}'.format( valid_domains ) )
    logger.info( 'MailboxTTL: {}'.format( mailboxTTL ) )

    origin = event.get( 'headers', { } ).get( 'origin', default_allowed_origin )
    username = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get(
            'cognito:username' )
    user_email = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'email' )

    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "GET,OPTIONS,POST",
        "access-control-allow-origin":  get_allowed_origins( origin )
    }

    message = "missing or invalid parameters"
    result = { "statusCode": 400,
               "body":       json.dumps( { "message": message } ),
               "headers":    headers
               }

    if user_email is None or username is None:
        return result

    disposable_address = event.get( 'queryStringParameters', { } ).get( 'address' )

    if disposable_address == "random" or validate_email( disposable_address ):
        if disposable_address == "random":
            disposable_address = generate_unique_random_email( )
            create_address( disposable_address, username, user_email )
            message = "random email address created"
        elif address_exists( disposable_address ):
            if user_owns_address( disposable_address, username ):
                message = "email address already exists"
            else:
                message = "email address already exists and is owned by another user, " \
                          "creating random address"
                disposable_address = generate_unique_random_email( )
                create_address( disposable_address, username, user_email )
        else:
            create_address( disposable_address, username, user_email )
            message = "email address created"

        result = {
            "statusCode": 200,
            "body":       json.dumps(
                    {
                        "message":      message,
                        "address":      disposable_address,
                        "allAddresses": get_all_addresses( username ) } ),
            "headers":    headers
        }

    return result
