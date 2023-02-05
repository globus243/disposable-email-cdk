import re
import boto3
from botocore.exceptions import ClientError
import json
import os
import logging

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

dynamodb = boto3.resource( "dynamodb" )
address_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )

cors_allowed_origins = os.environ[ 'cors_allowed_origins' ].split( ',' )
default_allowed_origin = cors_allowed_origins[ 0 ]


def extend_ttl( address, ttl ):
    """
    Extend the TTL of a given address by the given amount of time
    :param address: the display address to extend
    :param ttl: the amount of time to extend the TTL by, in seconds
    :raises ClientError: if the address does not exist
    """
    try:
        address_table.update_item(
                Key = {
                    'address': address
                },
                UpdateExpression = "set #value = :t",
                ExpressionAttributeNames = { "#value": "ttl" },
                ExpressionAttributeValues = { ":t": ttl }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )


def validate_email( address ):
    """
    check if a given email address is a valid email address
    :param address: the email address to validate
    :return: True if the email address is valid, False otherwise
    """
    if type( address ) is not str:
        return False
    if re.match( '^.+@(\\[?)[a-zA-Z0-9\\-.]+\\.([a-zA-Z]{2,3}|[0-9]{1,3})(]?)$', address ) is not None:
        return True
    return False


def change_redirect( disposable_address, redirect, redirect_email = "", ):
    """
    Change or remove the redirect for a disposable
    :param disposable_address: the disposable address to change
    :param redirect: True to enable redirect, False to disable
    :param redirect_email: the email to redirect to
    :return: True if the address was changed, False otherwise
    """
    try:
        address_table.update_item(
                Key = {
                    'address': disposable_address
                },
                UpdateExpression = "SET redirect = :r, redirect_email = :e",
                ExpressionAttributeValues = { ':r': redirect, ':e': redirect_email }
        )
    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )
        return False
    else:
        return True


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

    username = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'cognito:username' )
    user_email = event.get( 'requestContext', { } ).get( 'authorizer', { } ).get( 'claims', { } ).get( 'email' )

    disposable_address = event.get( 'pathParameters', { } ).get( 'destination' )

    body = json.loads( event.get( 'body', { } ) )
    action = body.get( "action" )

    headers = {
        "access-control-allow-headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "access-control-allow-methods": "GET,OPTIONS,POST",
        "access-control-allow-origin":  get_allowed_origins( origin )
    }

    result = { "statusCode": 400, "body": json.dumps( { "result": "missing parameters" } ), "headers": headers }

    if None in [ username, user_email, disposable_address, action ]:
        return result

    if user_owns_address( disposable_address, username ):
        if action == "extend":
            new_ttl = body.get( "ttl" )
            if new_ttl is not None:
                extend_ttl( disposable_address, new_ttl )
                result = { "statusCode": 200,
                           "body":       json.dumps(
                                   { "result": "success",
                                     "address": disposable_address,
                                     "new_ttl": new_ttl } ),
                           "headers":    headers }
        if action == "redirect":
            redirect_email = body.get( "redirect_email", None )
            redirect = body.get( "redirect", None )
            if redirect in [ True, False ] and redirect_email is not None:
                if change_redirect( disposable_address, redirect, redirect_email ):
                    result = { "statusCode": 200,
                               "body":       json.dumps(
                                       { "result":      "success",
                                         "address":     disposable_address,
                                         "redirect":    redirect,
                                         "redirect_to": redirect_email } ),
                               "headers":    headers }
    return result
