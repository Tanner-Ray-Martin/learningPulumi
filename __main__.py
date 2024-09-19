import pulumi
from pulumi_aws import s3, ecr, iam, ecs, apprunner
import pulumi_docker as docker
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


# Create an ECR repository for your Streamlit app
ecr_repo = ecr.Repository("streamlit-app-repo")

# Get the ECR repository URL
image_name = ecr_repo.repository_url

# Get ECR credentials
ecr_creds = ecr.get_authorization_token(registry_id=ecr_repo.registry_id)

# Define the absolute path to the build context
build_context_path = os.path.abspath("./streamlit_app")

# Ensure the build context path exists
if not os.path.exists(build_context_path):
    raise Exception(f"Build context path '{build_context_path}' does not exist.")

# Define the Docker image
streamlit_image = docker.Image(
    "streamlit-app-image",
    build=docker.DockerBuildArgs(
        context=build_context_path,
        dockerfile="streamlit_app/Dockerfile",
    ),
    image_name=image_name.apply(lambda name: f"{name}:latest"),
    registry=docker.RegistryArgs(
        server=image_name.apply(lambda name: name.split("/")[0]),
        username=ecr_creds.user_name,
        password=ecr_creds.password,
    ),
)

# Create an IAM role for App Runner to access ECR
app_runner_role = iam.Role(
    "apprunner-ecr-access-role",
    assume_role_policy="""{
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "build.apprunner.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }]
    }""",
)

# Attach the necessary policy to the role
iam.RolePolicyAttachment(
    "apprunner-ecr-access-policy",
    role=app_runner_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess",
)

# Create an AWS App Runner service
app_runner_service = apprunner.Service(
    "streamlit-app-service",
    service_name="streamlit-app-service",
    source_configuration=apprunner.ServiceSourceConfigurationArgs(
        authentication_configuration=apprunner.ServiceSourceConfigurationAuthenticationConfigurationArgs(
            access_role_arn=app_runner_role.arn,
        ),
        image_repository=apprunner.ServiceSourceConfigurationImageRepositoryArgs(
            image_identifier=streamlit_image.image_name,
            image_repository_type="ECR",
            image_configuration=apprunner.ServiceSourceConfigurationImageRepositoryImageConfigurationArgs(
                port="8501",
            ),
        ),
    ),
    instance_configuration=apprunner.ServiceInstanceConfigurationArgs(
        cpu="1024",  # Optional: Adjust as needed
        memory="2048",  # Optional: Adjust as needed
    ),
)

# Export the URL of the running App Runner service
pulumi.export("app_runner_service_url", app_runner_service.service_url)
