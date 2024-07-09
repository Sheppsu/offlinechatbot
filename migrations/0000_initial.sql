CREATE TABLE `afk` (
  `message` text,
  `time` text,
  `username` text
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `animecompare_games` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user` varchar(25) NOT NULL,
  `score` int NOT NULL DEFAULT '0',
  `finished` tinyint NOT NULL DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `id_UNIQUE` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3591 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `channels` (
  `name` varchar(25) NOT NULL,
  `id` int unsigned NOT NULL,
  `channel_inclusion` int unsigned NOT NULL DEFAULT '0',
  `offlineonly` tinyint unsigned NOT NULL DEFAULT '1',
  `commands` json NOT NULL,
  PRIMARY KEY (`name`),
  UNIQUE KEY `name_UNIQUE` (`name`),
  UNIQUE KEY `id_UNIQUE` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `lastfm` (
  `user_id` int unsigned NOT NULL,
  `lastfm_user` varchar(36) NOT NULL,
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `user_id_UNIQUE` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `messages` (
  `userid` int unsigned NOT NULL,
  `username` varchar(45) NOT NULL,
  `message` varchar(496) NOT NULL,
  `context` varchar(5410) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `old_userdata` (
  `username` varchar(25) NOT NULL,
  `money` int NOT NULL,
  PRIMARY KEY (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `osu_data` (
  `osu_user_id` int unsigned NOT NULL,
  `osu_username` varchar(45) NOT NULL,
  `verified` tinyint unsigned NOT NULL DEFAULT '0',
  `user_id` int unsigned NOT NULL,
  `rank` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`user_id`),
  UNIQUE KEY `user_id_UNIQUE` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `osu_user_data` (
  `osu_user_id` int unsigned NOT NULL,
  `global_rank` int unsigned DEFAULT NULL,
  PRIMARY KEY (`osu_user_id`),
  UNIQUE KEY `osu_user_id_UNIQUE` (`osu_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `pets` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `health` int unsigned NOT NULL DEFAULT '100',
  `hunger` int unsigned NOT NULL DEFAULT '100',
  `status` varchar(16) NOT NULL DEFAULT 'HEALTHY',
  PRIMARY KEY (`id`),
  UNIQUE KEY `id_UNIQUE` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `pity` (
  `username` text,
  `four` int DEFAULT '0',
  `five` int DEFAULT '0'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `reminders` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int unsigned NOT NULL,
  `end_time` text NOT NULL,
  `message` text,
  `channel` varchar(25) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id_UNIQUE` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=561 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `timezones` (
  `userid` int unsigned NOT NULL,
  `timezone` varchar(69) NOT NULL,
  PRIMARY KEY (`userid`),
  UNIQUE KEY `userid_UNIQUE` (`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
CREATE TABLE `userdata` (
  `username` varchar(25) NOT NULL,
  `money` int NOT NULL DEFAULT '0',
  `receive` tinyint(1) DEFAULT '1',
  `autoafk` tinyint(1) DEFAULT '1',
  `userid` int unsigned NOT NULL DEFAULT '0',
  PRIMARY KEY (`userid`),
  KEY `idx_user_metadata` (`username`,`userid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
