-- One-time, by hand, as ACCOUNTADMIN in a Snowsight worksheet: the service user Terraform signs in as.
-- Replace <PUBLIC_KEY> with the body of pets_terraform.pub (the lines between BEGIN and END, joined).
-- Everything else in Snowflake for Pets Central is created by Terraform from this folder.
--
-- Terraform needs ACCOUNTADMIN because only account administrators can create resource monitors. It only ever
-- touches the objects in this folder's configuration, all named PETS_*.

USE ROLE ACCOUNTADMIN;

CREATE USER IF NOT EXISTS PETS_TERRAFORM
    TYPE = SERVICE
    DEFAULT_ROLE = ACCOUNTADMIN
    RSA_PUBLIC_KEY = '<PUBLIC_KEY>'
    COMMENT = 'Terraform for Pets Central (infra/snowflake)';
GRANT ROLE ACCOUNTADMIN TO USER PETS_TERRAFORM;

-- What Terraform's settings need. Send these four values back.
SELECT CURRENT_ORGANIZATION_NAME() AS organization_name,
       CURRENT_ACCOUNT_NAME() AS account_name,
       CURRENT_REGION() AS region,
       CURRENT_USER() AS your_user;
