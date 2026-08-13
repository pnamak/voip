-- SmartVoIP branding defaults applied after MagnusBilling schema import.
UPDATE pkg_configuration SET config_value = 'en' WHERE config_key = 'base_language';
UPDATE pkg_configuration SET config_value = 'black-neptune' WHERE config_key = 'template';
UPDATE pkg_configuration SET config_value = 'White' WHERE config_key = 'color_menu';
UPDATE pkg_configuration SET config_value = '#07111f' WHERE config_key = 'backgroundColor';
UPDATE pkg_configuration SET config_value = 'Sign in to SmartVoIP' WHERE config_key = 'login_header';
UPDATE pkg_configuration SET config_value = 'support@smartvoip.local' WHERE config_key = 'admin_email';
UPDATE pkg_user
   SET company_name = 'SmartVoIP',
       commercial_name = 'SmartVoIP Billing Platform',
       email = 'support@smartvoip.local'
 WHERE username = 'root';
