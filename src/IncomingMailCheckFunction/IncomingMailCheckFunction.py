import boto3
from botocore.exceptions import ClientError
import os
import logging
import time

logger = logging.getLogger( )
logger.setLevel( logging.INFO )

dynamodb = boto3.resource( "dynamodb" )
addresses_table = dynamodb.Table( os.environ[ 'addresses_table_name' ] )
reply_addresses_table = dynamodb.Table( os.environ[ 'reply_addresses_table_name' ] )


def address_exists( address ):
    """
    Check if a given disposable email address exists in the database and is not expired.
    :param address: The disposable email address to check.
    :return: True if the address exists and is not expired, False otherwise.
    :raises: ClientError if the DynamoDB query fails.
    """
    try:
        response = addresses_table.get_item(
                Key = {
                    'address': address
                }
        )
        if 'Item' in response:
            item = response[ 'Item' ]
            if item[ 'ttl' ] > int( time.time( ) ):
                return True

        response = reply_addresses_table.get_item(
                Key = {
                    'proxyAddress': address
                }
        )
        if 'Item' in response:
            return True

    except ClientError as e:
        logger.info( '## DynamoDB Client Exception' )
        logger.info( e.response[ 'Error' ][ 'Message' ] )

    return False


def lambda_handler( event, context ):
    logger.info( '## ENVIRONMENT VARIABLES' )
    logger.info( os.environ )
    logger.info( '## EVENT' )
    logger.info( event )

    for record in event[ 'Records' ]:
        to_address = record[ 'ses' ][ 'mail' ][ 'destination' ][ 0 ]
        logger.info( '## DESTINATION' )
        logger.info( to_address )
        if address_exists( to_address ):
            return { 'disposition': 'CONTINUE' }
        else:
            return { 'disposition': 'STOP_RULE_SET' }
