import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key
import json
import os
import logging

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

dynamodb = boto3.resource( "dynamodb" )
emails_table = dynamodb.Table( os.environ[ 'emails_table_name' ] )
address_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )

cors_allowed_origins = os.environ[ 'cors_allowed_origins' ].split( ',' )
default_allowed_origin = cors_allowed_origins[ 0 ]


def get_emails( destination ):
    items = None
    try:
        filtering_exp = Key( 'destination' ).eq( destination )
        response = emails_table.query( KeyConditionExpression = filtering_exp )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        items = { 'items': response[ 'Items' ], 'count': response[ 'Count' ] }
    return items


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

    origin = event.get( 'headers' ).get( 'origin', default_allowed_origin )

    username = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'cognito:username' )
    user_email = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'email' )

    disposable_address = event.get( 'pathParameters', { } ).get( 'destination' )

    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "GET,OPTIONS,POST",
        "access-control-allow-origin":  get_allowed_origins( origin )
    }

    result = { "statusCode": 400,
               "body":       json.dumps( { "message": "missing or invalid parameters" } ),
               "headers":    headers
               }

    if None in [ username, user_email, disposable_address ]:
        return result

    if user_owns_address( disposable_address, username ):
        items = get_emails( disposable_address )
        result = { "statusCode": 200, "body": json.dumps( items ), "headers": headers }

    return result
