import boto3
from botocore.exceptions import ClientError
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

bucket_name = os.environ[ 'emails_bucket_name' ]

s3 = boto3.client( 's3' )


def get_email_data( destination, message_id ):
    """
    retrieves information about a given email from the database
    :param destination: the disposable email address the message was sent to
    :param message_id: the message ID
    :return:
    """
    result = None
    try:
        response = emails_table.get_item(
                Key = {
                    'destination': destination,
                    'messageId':   message_id
                }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
    else:
        if 'Item' in response:
            result = response[ 'Item' ]
    return result


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


def set_as_read( destination, message_id ):
    """
    toggle the isNew flag to false for a given message ID and destination
    :param destination: the disposable email address the message was sent to
    :param message_id: the message ID
    :raises ClientError: DynamoDB Client Exception
    """
    try:
        emails_table.update_item(
                Key = {
                    'destination': destination,
                    'messageId':   message_id
                },
                UpdateExpression = "SET isNew = :updated",
                ExpressionAttributeValues = { ':updated': False }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )


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
    username = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get(
        'cognito:username' )
    user_email = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'email' )

    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "GET,OPTIONS,POST",
        "access-control-allow-origin":  get_allowed_origins( origin )
    }

    result = { "statusCode": 400, "body": json.dumps( { "body": "missing parameters" } ), "headers": headers }

    if username is None or user_email is None:
        return result

    disposable_address = event.get( 'pathParameters', { } ).get( 'destination' )
    message_id = event.get( 'pathParameters', { } ).get( 'messageId' )

    if None not in [ disposable_address, message_id ] \
            and user_owns_address( disposable_address, username ):
        email_file = get_email_data( disposable_address, message_id )
        if email_file is not None:
            data = s3.get_object(
                    Bucket = bucket_name, Key = email_file.get( 'messageId' ) )
            contents = data.get( "Body" ).read( ).decode( 'utf-8' )
            headers.update( { "content-type": "message/rfc822" } )
            result = {
                "statusCode": 200,
                "headers":    headers,
                "body":       contents
            }
            if email_file.get( 'isNew' ):
                set_as_read( disposable_address, message_id )
        else:
            result = { "statusCode": 401, "body": json.dumps( { "message": "not found" } ),
                       "headers":    headers }

    return result
