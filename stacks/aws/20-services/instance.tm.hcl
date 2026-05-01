stack {
  name = "AWS Instance"

  tags = [
    "aws",
    "aws-services",
    "instance",
    "services",
  ]

  after = [
    "/stacks/aws/10-shared",
  ]
}

import {
  source = "/modules/aws/ec2/instance.tm.hcl"
}
