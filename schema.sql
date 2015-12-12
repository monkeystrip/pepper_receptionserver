create table if not exists appointment (
        id varchar(36) primary key,
        starttime text,
        endtime text,
        guestcompany text,
        guestname text,
        guestmail text,
        room text,
        ownername text,
        ownermail text,
        greeting varchar(36),
        visit integer
    );

create table if not exists greeting (
        id varchar(36) primary key,
        imagepath text,
        name text,
        speech text
    );

create table if not exists solitary (
        id integer primary key autoincrement,
        greeting varchar(36),
        enabled integer
    );

create table if not exists history (
        id integer primary key autoincrement,
        appointment varchar(36),
        time text
    );

    