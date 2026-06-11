-- 将现有 TikHub 配置从 service_credentials 迁移到 tikhub_credentials
DO $$
DECLARE
  sc_record RECORD;
  new_cred_id BIGINT;
BEGIN
  FOR sc_record IN
    SELECT id, label, secret_enc AS api_key, status, weight
    FROM service_credentials
    WHERE provider = 'tikhub'
  LOOP
    INSERT INTO tikhub_credentials (
      label, api_key, base_url, status, max_concurrent, max_users
    )
    VALUES (
      sc_record.label,
      sc_record.api_key,
      'https://api.tikhub.io',
      CASE WHEN sc_record.status = 'enabled' THEN 'active' ELSE 'inactive' END,
      5,
      10
    )
    RETURNING id INTO new_cred_id;

    RAISE NOTICE 'Migrated TikHub credential: % (old id: %, new id: %)', sc_record.label, sc_record.id, new_cred_id;
  END LOOP;
END $$;
