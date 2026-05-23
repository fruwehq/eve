stack {
  name = "AWS Instance"

  tags = [
    "aws",
    "aws-services",
    "instance",
    "services",
  ]

  after = [
    "/plugins/providers/aws/stacks/10-shared",
  ]
}

import {
  source = "/plugins/providers/aws/modules/ec2/instance.tm.hcl"
}
