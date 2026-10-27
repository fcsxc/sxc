import path from "node:path";
import { seekdb } from "@oceanbase/seekdb-node";
import mysql from "mysql2/promise";

export function seekdbPath() {
  return path.resolve(process.env.SEEKDB_PATH ?? "seekdb-data");
}

export async function withSeekdb(callback) {
  const db = await seekdb.open(seekdbPath());
  let connection;
  try {
    const endpoint = db.connectionOptions();
    const location = endpoint.transport === "tcp"
      ? { host: endpoint.host, port: endpoint.port }
      : {
          socketPath: endpoint.transport === "unix_socket"
            ? endpoint.unixSocket
            : endpoint.namedPipe,
        };
    connection = await mysql.createConnection({
      ...location,
      user: endpoint.user,
      password: "",
      database: "test",
      multipleStatements: false,
    });
    await connection.query(`
      CREATE TABLE IF NOT EXISTS engineering_docs (
        id VARCHAR(128) PRIMARY KEY,
        kind VARCHAR(24) NOT NULL,
        path VARCHAR(255) NOT NULL,
        symbol VARCHAR(128),
        content LONGTEXT NOT NULL,
        version VARCHAR(32) NOT NULL,
        updated_at DATETIME NOT NULL
      )
    `);
    return await callback({ connection, endpoint });
  } finally {
    if (connection) await connection.end();
    db.close();
  }
}
