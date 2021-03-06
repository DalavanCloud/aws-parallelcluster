import sys

import argparse
import boto3
import pkg_resources
from botocore.exceptions import ClientError


def get_all_aws_regions(partition):
    if partition == "commercial":
        region = "us-east-1"
    elif partition == "govcloud":
        region = "us-gov-west-1"
    elif partition == "china":
        region = "cn-north-1"
    else:
        print("Unsupported partition %s" % partition)
        sys.exit(1)

    ec2 = boto3.client("ec2", region_name=region)
    return set(sorted(r.get("RegionName") for r in ec2.describe_regions().get("Regions")))


def put_object_to_s3(s3_client, bucket, key, region, data, template_name):
    try:
        object = s3_client.Object(bucket, key)
        response = object.put(Body=data, ACL="public-read")
        if response.get("ResponseMetadata").get("HTTPStatusCode") == 200:
            print("Successfully uploaded %s to s3://%s/%s" % (template_name, bucket, key))
    except ClientError as e:
        if args.createifnobucket and e.response["Error"]["Code"] == "NoSuchBucket":
            print("No bucket, creating now: ")
            if region == "us-east-1":
                s3_client.create_bucket(Bucket=bucket)
            else:
                s3_client.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
            s3_client.BucketVersioning(bucket).enable()
            print("Created %s bucket. Bucket versioning is enabled, " "please enable bucket logging manually." % bucket)
            b = s3_client.Bucket(bucket)
            res = b.put_object(Body=data, ACL="public-read", Key=key)
            print(res)
        else:
            print("Couldn't upload %s to bucket s3://%s/%s" % (template_name, bucket, key))
            if e.response["Error"]["Code"] == "NoSuchBucket":
                print("Bucket is not present.")
            else:
                raise e
        pass


def upload_to_s3(args, region):
    s3_client = boto3.resource("s3", region_name=region)

    if args.bucket:
        buckets = args.bucket.split(",")
    else:
        buckets = ["%s-aws-parallelcluster" % region]
    key_path = "templates/"
    template_paths = "cloudformation/"

    for t in args.templates:
        template_name = "%s%s.cfn.json" % (template_paths, t)
        key = key_path + "%s-%s.cfn.json" % (t, args.version)
        data = open(template_name, "rb")
        for bucket in buckets:
            try:
                s3 = boto3.client("s3", region_name=region)
                s3.head_object(Bucket=bucket, Key=key)
                print("Warning: %s already exist in bucket %s" % (key, bucket))
                exist = True
            except ClientError:
                exist = False
                pass

            if (exist and args.override and not args.dryrun) or (not exist and not args.dryrun):
                put_object_to_s3(s3_client, bucket, key, region, data, template_name)
            else:
                print(
                    "Not uploading %s to bucket %s, object exists %s, override is %s, dryrun is %s"
                    % (template_name, bucket, exist, args.override, args.dryrun)
                )


def main(args):
    # For all regions
    for region in args.regions:
        upload_to_s3(args, region)


if __name__ == "__main__":
    # parse inputs
    parser = argparse.ArgumentParser(description="Upload extra templates under /cloudformation")
    parser.add_argument("--partition", type=str, help="commercial | china | govcloud", required=True)
    parser.add_argument(
        "--regions",
        type=str,
        help='Valid Regions, can include "all", or comma separated list of regions',
        required=True,
    )
    parser.add_argument(
        "--templates", type=str, help="Template filenames, leave out '.cfn.json', comma separated list", required=True
    )
    parser.add_argument(
        "--bucket",
        type=str,
        help="Buckets to upload to, defaults to [region]-aws-parallelcluster, comma separated list",
        required=False,
    )
    parser.add_argument(
        "--dryrun", action="store_true", help="Doesn't push anything to S3, just outputs", default=False, required=False
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="If override is false, the file will not be pushed if it already exists in the bucket",
        default=False,
        required=False,
    )
    parser.add_argument(
        "--createifnobucket",
        action="store_true",
        help="Create S3 bucket if it does not exist",
        default=False,
        required=False,
    )
    parser.add_argument(
        "--unsupportedregions", type=str, help="Unsupported regions, comma separated", default="", required=False
    )
    args = parser.parse_args()
    args.version = pkg_resources.get_distribution("aws-parallelcluster").version

    if args.regions == "all":
        args.regions = get_all_aws_regions(args.partition)
    else:
        args.regions = args.regions.split(",")
    args.regions = set(args.regions) - set(args.unsupportedregions.split(","))

    args.templates = args.templates.split(",")

    main(args)
