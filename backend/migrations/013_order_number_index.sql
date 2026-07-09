-- Index u_order_number for Sales Order Analyze local lookup performance
CREATE INDEX IF NOT EXISTS idx_rexus_incidents_v3_u_order_number
    ON rexus_incidents_v3 (u_order_number)
    WHERE u_order_number IS NOT NULL AND u_order_number <> '';

CREATE INDEX IF NOT EXISTS idx_rexus_incidents_new_u_order_number
    ON rexus_incidents_new (u_order_number)
    WHERE u_order_number IS NOT NULL AND u_order_number <> '';
