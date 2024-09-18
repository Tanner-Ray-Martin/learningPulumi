import pulumi
from pulumi_aws import s3
import mimetypes
import os

bucket_name = "jwst-images"


def public_read_policy_for_bucket(bucket_arn):
    return bucket_arn.apply(
        lambda arn: pulumi.Output.json_dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["s3:GetObject"],
                        "Resource": [f"{arn}/*"],
                    }
                ],
            }
        )
    )


# Create an AWS resource (S3 Bucket)
bucket = s3.Bucket(bucket_name)

# Export the name of the bucket
pulumi.export("bucket_name", bucket.id)

for f in os.listdir("images"):
    clean_f = f.replace(" ", "-").lower().strip()
    mime_type, _ = mimetypes.guess_type(f"images/{f}")

    bucket_object = s3.BucketObject(
        clean_f,
        bucket=bucket.id,
        content_type=mime_type,
        key=clean_f,
        source=pulumi.FileAsset(f"images/{f}"),
    )

    pulumi.export(
        clean_f.split(".")[0],
        pulumi.Output.concat(
            "https://", bucket.id, ".s3.amazonaws.com", "/", bucket_object.id
        ),
    )

bucket_policy = s3.BucketPolicy(
    f"{bucket_name}-policy",
    bucket=bucket.id,
    policy=public_read_policy_for_bucket(
        pulumi.Output.concat("arn:aws:s3:::", bucket.id)
    ),
)
