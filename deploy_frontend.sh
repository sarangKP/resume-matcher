#!/usr/bin/env bash
# Uploads the frontend to S3 and clears the CloudFront cache.
# Run after: sam build && sam deploy
set -euo pipefail

STACK=resume-matcher
REGION=ap-south-1

out() {
  aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

BUCKET=$(out FrontendBucketName)
DIST=$(out DistributionId)
API=$(out FunctionUrl)

# config.js is gitignored, so it is generated here from the stack output
echo "const API_URL = \"$API\";" > frontend/config.js

aws s3 sync frontend/ "s3://$BUCKET/" --delete --region "$REGION"
aws cloudfront create-invalidation --distribution-id "$DIST" --paths "/*" >/dev/null

echo "Done: $(out SiteUrl)"
