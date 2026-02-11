-- One table per underlying (replace __TABLE_NAME__ with e.g. option_snapshots_SPX).
-- Run against your OptionData database (app can create DB if missing)

IF NOT EXISTS (
    SELECT * FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'dbo' AND t.name = '__TABLE_NAME__'
)
BEGIN
    CREATE TABLE dbo.__TABLE_NAME__ (
        id BIGINT IDENTITY(1,1) NOT NULL,
        expiration_date DATE NOT NULL,
        strike FLOAT NOT NULL,
        option_type NCHAR(1) NOT NULL,  -- 'C' or 'P'
        bid FLOAT NOT NULL,
        ask FLOAT NOT NULL,
        last FLOAT NOT NULL,
        snapshot_utc DATETIME2 NOT NULL,
        CONSTRAINT PK___TABLE_NAME___id PRIMARY KEY (id)
    );

    CREATE NONCLUSTERED INDEX IX___TABLE_NAME___lookup
        ON dbo.__TABLE_NAME__ (expiration_date, strike, option_type, snapshot_utc);
END
GO
