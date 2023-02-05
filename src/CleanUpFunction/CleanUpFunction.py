import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
import os
import logging
import time

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

dynamodb = boto3.resource( "dynamodb" )
s3 = boto3.client( 's3' )

addresses_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )
emails_table = dynamodb.Table( os.environ[ 'emails_table_name' ] )  # noqa
reply_addresses_table = dynamodb.Table( os.environ[ 'reply_addresses_table_name' ] )

bucket_name = os.environ[ 'emails_bucket_name' ]


def delete_object( bucket, object_name ):
    """Delete an object from an S3 bucket

    :param bucket: string
    :param object_name: string
    :return: True if the referenced object was deleted, otherwise False
    """
    logger.info( '## Deleting S3' )
    logger.info( bucket + object_name )

    # Delete the object
    try:
        s3.delete_object( Bucket = bucket, Key = object_name )
    except ClientError as e:
        logger.error( e )
        return False
    return True


def delete_email_item( destination, message_id ):
    """
    Delete an email item from the emails table
    :param destination: disposable address
    :param message_id: message id to delete
    :raises ClientError: DynamoDB client error
    """
    try:
        emails_table.delete_item(
                Key = {
                    'destination': destination,
                    'messageId':   message_id
                }
        )
    except ClientError as e:
        logger.error( '## DynamoDB Client Exception' )
        logger.error( e.response[ 'Error' ][ 'Message' ] )


def delete_reply_address_item( disposable_address ):
    """
    Deletes all redirect addresses for a disposable address

    :param disposable_address: disposable address
    :raises ClientError: DynamoDB client error
    """
    try:
        response = reply_addresses_table.scan(
                FilterExpression = Attr( 'disposableAddress' ).eq( disposable_address ),
                ProjectionExpression = "proxyAddress"
        )
    except ClientError as e:
        logger.error( '## DynamoDB Client Exception' )
        logger.error( e.response[ 'Error' ][ 'Message' ] )
    else:
        for i in response[ 'Items' ]:
            reply_addresses_table.delete_item(
                    Key = {
                        'proxyAddress': i[ 'proxyAddress' ]
                    }
            )


def delete_address_item( address ):
    """
    Deletes a disposable address from the addresses table

    :param address: disposable address to delete
    :raises ClientError: DynamoDB client error
    """
    try:
        addresses_table.delete_item(
                Key = {
                    'address': address
                }
        )
    except ClientError as e:
        logger.error( '## DynamoDB Client Exception' )
        logger.error( e.response[ 'Error' ][ 'Message' ] )


def delete_emails( destination ):
    """
    Deletes all emails for a disposable address in the emails table and S3 bucket

    :param destination: disposable address
    :raises ClientError: DynamoDB client error
    """
    try:
        response = emails_table.query(
                KeyConditionExpression = Key( 'destination' ).eq( destination ),
                ProjectionExpression = "messageId"
        )
    except ClientError as e:
        logger.error( '## DynamoDB Client Exception' )
        logger.error( e.response[ 'Error' ][ 'Message' ] )
    else:
        # Clean response
        for i in response[ 'Items' ]:
            delete_object( bucket_name, i[ 'messageId' ] )
            delete_email_item( destination, i[ 'messageId' ] )


def cleanup( ):
    """
    Deletes all disposable addresses, emails from the database and Bucket, that are expired

    :raises ClientError: DynamoDB client error
    """
    try:
        response = addresses_table.scan(
                FilterExpression = Attr( 'ttl' ).lt( int( time.time( ) ) ),
                ProjectionExpression = "address"
        )
    except ClientError as e:
        logger.error( '## DynamoDB Client Exception' )
        logger.error( e.response[ 'Error' ][ 'Message' ] )
    else:
        for i in response[ 'Items' ]:
            delete_emails( i[ 'address' ] )
            delete_address_item( i[ 'address' ] )
            delete_reply_address_item( i[ 'address' ] )


def lambda_handler( event, context ):
    logger.info( '## ENVIRONMENT VARIABLES' )
    logger.info( os.environ )
    logger.info( '## EVENT' )
    logger.info( event )

    result = { "statusCode": 200, "body": "cleanup" }
    cleanup( )

    return result
