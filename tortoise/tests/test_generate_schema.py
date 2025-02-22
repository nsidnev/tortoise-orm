# pylint: disable=C0301
import re
import sys
import warnings

from asynctest.mock import CoroutineMock, patch

from tortoise import Tortoise
from tortoise.contrib import test
from tortoise.exceptions import ConfigurationError
from tortoise.utils import get_schema_sql


class TestGenerateSchema(test.SimpleTestCase):
    async def setUp(self):
        try:
            Tortoise.apps = {}
            Tortoise._connections = {}
            Tortoise._inited = False
        except ConfigurationError:
            pass
        Tortoise._inited = False
        self.sqls = ""
        self.post_sqls = ""
        self.engine = test.getDBConfig(app_label="models", modules=[])["connections"]["models"][
            "engine"
        ]

    async def tearDown(self):
        Tortoise._connections = {}
        await Tortoise._reset_apps()

    async def init_for(self, module: str, safe=False) -> None:
        with patch(
            "tortoise.backends.sqlite.client.SqliteClient.create_connection", new=CoroutineMock()
        ):
            await Tortoise.init(
                {
                    "connections": {
                        "default": {
                            "engine": "tortoise.backends.sqlite",
                            "credentials": {"file_path": ":memory:"},
                        }
                    },
                    "apps": {"models": {"models": [module], "default_connection": "default"}},
                }
            )
            self.sqls = get_schema_sql(Tortoise._connections["default"], safe).split(";\n")

    def get_sql(self, text: str) -> str:
        return re.sub(r"[ \t\n\r]+", " ", " ".join([sql for sql in self.sqls if text in sql]))

    async def test_noid(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql('"noid"')
        self.assertIn('"name" VARCHAR(255)', sql)
        self.assertIn('"id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL', sql)

    async def test_minrelation(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql('"minrelation"')
        self.assertIn(
            '"tournament_id" SMALLINT NOT NULL REFERENCES "tournament" (id) ON DELETE CASCADE', sql
        )
        self.assertNotIn("participants", sql)

        sql = self.get_sql('"minrelation_team"')
        self.assertIn(
            '"minrelation_id" INT NOT NULL REFERENCES "minrelation" (id) ON DELETE CASCADE', sql
        )
        self.assertIn('"team_id" INT NOT NULL REFERENCES "team" (id) ON DELETE CASCADE', sql)

    async def test_safe_generation(self):
        """Assert that the IF NOT EXISTS clause is included when safely generating schema."""
        await self.init_for("tortoise.tests.testmodels", True)
        sql = self.get_sql("")
        self.assertIn("IF NOT EXISTS", sql)

    async def test_unsafe_generation(self):
        """Assert that the IF NOT EXISTS clause is not included when generating schema."""
        await self.init_for("tortoise.tests.testmodels", False)
        sql = self.get_sql("")
        self.assertNotIn("IF NOT EXISTS", sql)

    async def test_cyclic(self):
        with self.assertRaisesRegex(
            ConfigurationError, "Can't create schema due to cyclic fk references"
        ):
            await self.init_for("tortoise.tests.models_cyclic")

    @staticmethod
    def continue_if_safe_indexes(supported: bool):
        db = Tortoise.get_connection("default")
        if db.capabilities.safe_indexes != supported:
            raise test.SkipTest("safe_indexes != {}".format(supported))

    async def test_create_index(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("CREATE INDEX")
        self.assertIsNotNone(re.search(r"tournament_created_\w+_idx", sql))

    async def test_index_safe(self):
        await self.init_for("tortoise.tests.testmodels", safe=True)
        self.continue_if_safe_indexes(supported=True)
        sql = self.get_sql("CREATE INDEX")
        self.assertIn("IF NOT EXISTS", sql)

    async def test_safe_index_not_created_if_not_supported(self):
        await self.init_for("tortoise.tests.testmodels", safe=True)
        self.continue_if_safe_indexes(supported=False)
        sql = self.get_sql("")
        self.assertNotIn("CREATE INDEX", sql)

    async def test_fk_bad_model_name(self):
        with self.assertRaisesRegex(
            ConfigurationError, 'Foreign key accepts model name in format "app.Model"'
        ):
            await self.init_for("tortoise.tests.models_fk_1")

    async def test_fk_bad_on_delete(self):
        with self.assertRaisesRegex(
            ConfigurationError, "on_delete can only be CASCADE, RESTRICT or SET_NULL"
        ):
            await self.init_for("tortoise.tests.models_fk_2")

    async def test_fk_bad_null(self):
        with self.assertRaisesRegex(
            ConfigurationError, "If on_delete is SET_NULL, then field must have null=True set"
        ):
            await self.init_for("tortoise.tests.models_fk_3")

    async def test_m2m_bad_model_name(self):
        with self.assertRaisesRegex(
            ConfigurationError, 'Foreign key accepts model name in format "app.Model"'
        ):
            await self.init_for("tortoise.tests.models_m2m_1")

    async def test_table_and_row_comment_generation(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("comments")
        self.assertRegex(sql, r".*\/\* Upvotes done on the comment.*\*\/")
        self.assertRegex(sql, r".*\\n.*")
        self.assertIn("\\/", sql)

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        sql = get_schema_sql(Tortoise.get_connection("default"), safe=False)
        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE "defaultpk" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "val" INT NOT NULL
);
CREATE TABLE "sometable" (
    "sometable_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "some_chars_table" VARCHAR(255) NOT NULL,
    "fk_sometable" INT REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE INDEX "sometable_some_ch_115115_idx" ON "sometable" (some_chars_table);
CREATE TABLE "team" (
    "name" VARCHAR(50) NOT NULL  PRIMARY KEY /* The TEAM name (and PK) */,
    "manager_id" VARCHAR(50) REFERENCES "team" (name) ON DELETE CASCADE
) /* The TEAMS! */;
CREATE TABLE "tournament" (
    "tid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL  /* Tournament name */,
    "created" TIMESTAMP NOT NULL  /* Created *\\/'`\\/* datetime */
) /* What Tournaments *\\/'`\\/* we have */;
CREATE INDEX "tournament_name_116110_idx" ON "tournament" (name);
CREATE TABLE "event" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL /* Event ID */,
    "name" TEXT NOT NULL UNIQUE,
    "modified" TIMESTAMP NOT NULL,
    "prize" VARCHAR(40),
    "token" VARCHAR(100) NOT NULL UNIQUE /* Unique token */,
    "tournament_id" SMALLINT NOT NULL REFERENCES "tournament" (tid) ON DELETE CASCADE /* FK to tournament */
) /* This table contains a list of all the events */;
CREATE TABLE "sometable_self" (
    "backward_sts" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE,
    "sts_forward" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE TABLE "team_team" (
    "team_rel_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
CREATE TABLE "teamevents" (
    "event_id" BIGINT NOT NULL REFERENCES "event" (id) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
) /* How participants relate */;
""".strip(),  # noqa
        )

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema_safe(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        sql = get_schema_sql(Tortoise.get_connection("default"), safe=True)
        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE IF NOT EXISTS "defaultpk" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "val" INT NOT NULL
);
CREATE TABLE IF NOT EXISTS "sometable" (
    "sometable_id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "some_chars_table" VARCHAR(255) NOT NULL,
    "fk_sometable" INT REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "sometable_some_ch_115115_idx" ON "sometable" (some_chars_table);
CREATE TABLE IF NOT EXISTS "team" (
    "name" VARCHAR(50) NOT NULL  PRIMARY KEY /* The TEAM name (and PK) */,
    "manager_id" VARCHAR(50) REFERENCES "team" (name) ON DELETE CASCADE
) /* The TEAMS! */;
CREATE TABLE IF NOT EXISTS "tournament" (
    "tid" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "name" TEXT NOT NULL  /* Tournament name */,
    "created" TIMESTAMP NOT NULL  /* Created *\\/'`\\/* datetime */
) /* What Tournaments *\\/'`\\/* we have */;
CREATE INDEX IF NOT EXISTS "tournament_name_116110_idx" ON "tournament" (name);
CREATE TABLE IF NOT EXISTS "event" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL /* Event ID */,
    "name" TEXT NOT NULL UNIQUE,
    "modified" TIMESTAMP NOT NULL,
    "prize" VARCHAR(40),
    "token" VARCHAR(100) NOT NULL UNIQUE /* Unique token */,
    "tournament_id" SMALLINT NOT NULL REFERENCES "tournament" (tid) ON DELETE CASCADE /* FK to tournament */
) /* This table contains a list of all the events */;
CREATE TABLE IF NOT EXISTS "sometable_self" (
    "backward_sts" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE,
    "sts_forward" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "team_team" (
    "team_rel_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "teamevents" (
    "event_id" BIGINT NOT NULL REFERENCES "event" (id) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
) /* How participants relate */;
""".strip(),  # noqa
        )


class TestGenerateSchemaMySQL(TestGenerateSchema):
    async def init_for(self, module: str, safe=False) -> None:
        try:
            with patch("aiomysql.connect", new=CoroutineMock()):
                await Tortoise.init(
                    {
                        "connections": {
                            "default": {
                                "engine": "tortoise.backends.mysql",
                                "credentials": {
                                    "database": "test",
                                    "host": "127.0.0.1",
                                    "password": "foomip",
                                    "port": 3306,
                                    "user": "root",
                                    "connect_timeout": 1.5,
                                    "charset": "utf8mb4",
                                },
                            }
                        },
                        "apps": {"models": {"models": [module], "default_connection": "default"}},
                    }
                )
                self.sqls = get_schema_sql(Tortoise._connections["default"], safe).split("; ")
        except ImportError:
            raise test.SkipTest("aiomysql not installed")

    async def test_noid(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("`noid`")
        self.assertIn("`name` VARCHAR(255)", sql)
        self.assertIn("`id` INT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT", sql)

    async def test_minrelation(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("`minrelation`")
        self.assertIn(
            "`tournament_id` SMALLINT NOT NULL REFERENCES `tournament` (`id`) ON DELETE CASCADE",
            sql,
        )
        self.assertNotIn("participants", sql)

        sql = self.get_sql("`minrelation_team`")
        self.assertIn(
            "`minrelation_id` INT NOT NULL REFERENCES `minrelation` (`id`) ON DELETE CASCADE", sql
        )
        self.assertIn("`team_id` INT NOT NULL REFERENCES `team` (`id`) ON DELETE CASCADE", sql)

    async def test_table_and_row_comment_generation(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("comments")
        self.assertIn("COMMENT='Test Table comment'", sql)
        self.assertIn("COMMENT 'This column acts as it\\'s own comment'", sql)
        self.assertRegex(sql, r".*\\n.*")
        self.assertRegex(sql, r".*it\\'s.*")

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        sql = get_schema_sql(Tortoise.get_connection("default"), safe=False)
        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE `defaultpk` (
    `id` INT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `val` INT NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE `sometable` (
    `sometable_id` INT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `some_chars_table` VARCHAR(255) NOT NULL,
    `fk_sometable` INT REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE INDEX `sometable_some_ch_115115_idx` ON `sometable` (some_chars_table);
CREATE TABLE `team` (
    `name` VARCHAR(50) NOT NULL  COMMENT 'The TEAM name (and PK)',
    `manager_id` VARCHAR(50) REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='The TEAMS!';
CREATE TABLE `tournament` (
    `tid` SMALLINT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` TEXT NOT NULL  COMMENT 'Tournament name',
    `created` DATETIME(6) NOT NULL  COMMENT 'Created */\\'`/* datetime'
) CHARACTER SET utf8mb4 COMMENT='What Tournaments */\\'`/* we have';
CREATE INDEX `tournament_name_116110_idx` ON `tournament` (name);
CREATE TABLE `event` (
    `id` BIGINT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT 'Event ID',
    `name` TEXT NOT NULL UNIQUE,
    `modified` DATETIME(6) NOT NULL,
    `prize` DECIMAL(10,2),
    `token` VARCHAR(100) NOT NULL UNIQUE COMMENT 'Unique token',
    `tournament_id` SMALLINT NOT NULL COMMENT 'FK to tournament' REFERENCES `tournament` (`tid`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='This table contains a list of all the events';
CREATE TABLE `sometable_self` (
    `backward_sts` INT NOT NULL REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE,
    `sts_forward` INT NOT NULL REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE `team_team` (
    `team_rel_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE,
    `team_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE `teamevents` (
    `event_id` BIGINT NOT NULL REFERENCES `event` (`id`) ON DELETE CASCADE,
    `team_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='How participants relate';
""".strip(),  # noqa
        )

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema_safe(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        with warnings.catch_warnings(record=True) as w:
            with self.assertLogs("tortoise", level="WARNING") as cm:
                sql = get_schema_sql(Tortoise.get_connection("default"), safe=True)

        self.assertEqual(
            cm.output,
            [
                "WARNING:tortoise:CREATE INDEX `sometable_some_ch_115115_idx` ON `sometable`"
                " (some_chars_table);",
                "WARNING:tortoise:CREATE INDEX `tournament_name_116110_idx` ON `tournament`"
                " (name);",
            ],
        )

        self.assertEqual(len(w), 1)
        self.assertEqual(w[0].category, UserWarning)
        self.assertEqual(
            str(w[0].message),
            "Skipping creation of field indexes: safe index creation is not supported yet for"
            " mysql. Please find the SQL queries to create the indexes in the logs.",
        )

        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE IF NOT EXISTS `defaultpk` (
    `id` INT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `val` INT NOT NULL
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `sometable` (
    `sometable_id` INT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `some_chars_table` VARCHAR(255) NOT NULL,
    `fk_sometable` INT REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `team` (
    `name` VARCHAR(50) NOT NULL  COMMENT 'The TEAM name (and PK)',
    `manager_id` VARCHAR(50) REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='The TEAMS!';
CREATE TABLE IF NOT EXISTS `tournament` (
    `tid` SMALLINT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `name` TEXT NOT NULL  COMMENT 'Tournament name',
    `created` DATETIME(6) NOT NULL  COMMENT 'Created */\\'`/* datetime'
) CHARACTER SET utf8mb4 COMMENT='What Tournaments */\\'`/* we have';
CREATE TABLE IF NOT EXISTS `event` (
    `id` BIGINT UNSIGNED NOT NULL PRIMARY KEY AUTO_INCREMENT COMMENT 'Event ID',
    `name` TEXT NOT NULL UNIQUE,
    `modified` DATETIME(6) NOT NULL,
    `prize` DECIMAL(10,2),
    `token` VARCHAR(100) NOT NULL UNIQUE COMMENT 'Unique token',
    `tournament_id` SMALLINT NOT NULL COMMENT 'FK to tournament' REFERENCES `tournament` (`tid`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='This table contains a list of all the events';
CREATE TABLE IF NOT EXISTS `sometable_self` (
    `backward_sts` INT NOT NULL REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE,
    `sts_forward` INT NOT NULL REFERENCES `sometable` (`sometable_id`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `team_team` (
    `team_rel_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE,
    `team_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4;
CREATE TABLE IF NOT EXISTS `teamevents` (
    `event_id` BIGINT NOT NULL REFERENCES `event` (`id`) ON DELETE CASCADE,
    `team_id` VARCHAR(50) NOT NULL REFERENCES `team` (`name`) ON DELETE CASCADE
) CHARACTER SET utf8mb4 COMMENT='How participants relate';
""".strip(),  # noqa
        )


class TestGenerateSchemaPostgresSQL(TestGenerateSchema):
    async def init_for(self, module: str, safe=False) -> None:
        try:
            with patch("asyncpg.connect", new=CoroutineMock()):
                await Tortoise.init(
                    {
                        "connections": {
                            "default": {
                                "engine": "tortoise.backends.asyncpg",
                                "credentials": {
                                    "database": "test",
                                    "host": "127.0.0.1",
                                    "password": "foomip",
                                    "port": 3306,
                                    "user": "root",
                                },
                            }
                        },
                        "apps": {"models": {"models": [module], "default_connection": "default"}},
                    }
                )
                self.sqls = get_schema_sql(Tortoise._connections["default"], safe).split("; ")
        except ImportError:
            raise test.SkipTest("asyncpg not installed")

    async def test_noid(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql('"noid"')
        self.assertIn('"name" VARCHAR(255)', sql)
        self.assertIn('"id" SERIAL NOT NULL PRIMARY KEY', sql)

    async def test_table_and_row_comment_generation(self):
        await self.init_for("tortoise.tests.testmodels")
        sql = self.get_sql("comments")
        self.assertIn("COMMENT ON TABLE comments IS 'Test Table comment'", sql)
        self.assertIn(
            "COMMENT ON COLUMN comments.escaped_comment_field IS "
            "'This column acts as it''s own comment'",
            sql,
        )
        self.assertIn("COMMENT ON COLUMN comments.multiline_comment IS 'Some \\n comment'", sql)

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        sql = get_schema_sql(Tortoise.get_connection("default"), safe=False)
        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE "defaultpk" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "val" INT NOT NULL
);
CREATE TABLE "sometable" (
    "sometable_id" SERIAL NOT NULL PRIMARY KEY,
    "some_chars_table" VARCHAR(255) NOT NULL,
    "fk_sometable" INT REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE INDEX "sometable_some_ch_115115_idx" ON "sometable" (some_chars_table);
CREATE TABLE "team" (
    "name" VARCHAR(50) NOT NULL  PRIMARY KEY,
    "manager_id" VARCHAR(50) REFERENCES "team" (name) ON DELETE CASCADE
);
COMMENT ON COLUMN team.name IS 'The TEAM name (and PK)';
COMMENT ON TABLE team IS 'The TEAMS!';
CREATE TABLE "tournament" (
    "tid" SMALLSERIAL NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "created" TIMESTAMP NOT NULL
);
CREATE INDEX "tournament_name_116110_idx" ON "tournament" (name);
COMMENT ON COLUMN tournament.name IS 'Tournament name';
COMMENT ON COLUMN tournament.created IS 'Created */''`/* datetime';
COMMENT ON TABLE tournament IS 'What Tournaments */''`/* we have';
CREATE TABLE "event" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL UNIQUE,
    "modified" TIMESTAMP NOT NULL,
    "prize" DECIMAL(10,2),
    "token" VARCHAR(100) NOT NULL UNIQUE,
    "tournament_id" SMALLINT NOT NULL REFERENCES "tournament" (tid) ON DELETE CASCADE
);
COMMENT ON COLUMN event.id IS 'Event ID';
COMMENT ON COLUMN event.token IS 'Unique token';
COMMENT ON COLUMN event.tournament_id IS 'FK to tournament';
COMMENT ON TABLE event IS 'This table contains a list of all the events';
CREATE TABLE "sometable_self" (
    "backward_sts" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE,
    "sts_forward" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE TABLE "team_team" (
    "team_rel_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
CREATE TABLE "teamevents" (
    "event_id" BIGINT NOT NULL REFERENCES "event" (id) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
COMMENT ON TABLE teamevents IS 'How participants relate';
""".strip(),
        )

    @test.skipIf(sys.version_info < (3, 6), "Dict not sorted in 3.5")
    async def test_schema_safe(self):
        self.maxDiff = None
        await self.init_for("tortoise.tests.models_schema_create")
        sql = get_schema_sql(Tortoise.get_connection("default"), safe=True)
        self.assertEqual(
            sql.strip(),
            """
CREATE TABLE IF NOT EXISTS "defaultpk" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "val" INT NOT NULL
);
CREATE TABLE IF NOT EXISTS "sometable" (
    "sometable_id" SERIAL NOT NULL PRIMARY KEY,
    "some_chars_table" VARCHAR(255) NOT NULL,
    "fk_sometable" INT REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS "sometable_some_ch_115115_idx" ON "sometable" (some_chars_table);
CREATE TABLE IF NOT EXISTS "team" (
    "name" VARCHAR(50) NOT NULL  PRIMARY KEY,
    "manager_id" VARCHAR(50) REFERENCES "team" (name) ON DELETE CASCADE
);
COMMENT ON COLUMN team.name IS 'The TEAM name (and PK)';
COMMENT ON TABLE team IS 'The TEAMS!';
CREATE TABLE IF NOT EXISTS "tournament" (
    "tid" SMALLSERIAL NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL,
    "created" TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS "tournament_name_116110_idx" ON "tournament" (name);
COMMENT ON COLUMN tournament.name IS 'Tournament name';
COMMENT ON COLUMN tournament.created IS 'Created */''`/* datetime';
COMMENT ON TABLE tournament IS 'What Tournaments */''`/* we have';
CREATE TABLE IF NOT EXISTS "event" (
    "id" BIGSERIAL NOT NULL PRIMARY KEY,
    "name" TEXT NOT NULL UNIQUE,
    "modified" TIMESTAMP NOT NULL,
    "prize" DECIMAL(10,2),
    "token" VARCHAR(100) NOT NULL UNIQUE,
    "tournament_id" SMALLINT NOT NULL REFERENCES "tournament" (tid) ON DELETE CASCADE
);
COMMENT ON COLUMN event.id IS 'Event ID';
COMMENT ON COLUMN event.token IS 'Unique token';
COMMENT ON COLUMN event.tournament_id IS 'FK to tournament';
COMMENT ON TABLE event IS 'This table contains a list of all the events';
CREATE TABLE IF NOT EXISTS "sometable_self" (
    "backward_sts" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE,
    "sts_forward" INT NOT NULL REFERENCES "sometable" (sometable_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "team_team" (
    "team_rel_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "teamevents" (
    "event_id" BIGINT NOT NULL REFERENCES "event" (id) ON DELETE CASCADE,
    "team_id" VARCHAR(50) NOT NULL REFERENCES "team" (name) ON DELETE CASCADE
);
COMMENT ON TABLE teamevents IS 'How participants relate';
""".strip(),
        )
