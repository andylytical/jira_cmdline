#!/usr/bin/env python

import getpass
import sys
import argparse
import fileinput
import pprint
import os
import ConfigParser
import jira


# module level varibale to hold jira connection
conn = None
# module level variable to hold cmdline args
args = None


def parse_cmdline():
    desc = "List or modify jira tickets."
    epilog = """List or modify jira tickets.  Ticket ID's can be passed on cmdline or
        stdin.  The \"Modification\" options require a list of tickets to be
        given.  The \"List\" options can operate on a given set of tickets 
        (via cmdline or stdin), or when ticket id's are not given, will search
        the jira server for tickets assigned to the user (--list) 
        or the project (--list_all).  Default action is list."""
    parser = argparse.ArgumentParser( description=desc, epilog=epilog )
    parser.add_argument( 'ticketlist',
                         metavar='TICKET_ID',
                         nargs='*',
                         help="ticket id's to operate on, if empty, stdin is used")
    parser.add_argument('--usersearch',
                        metavar='NAME',
                        help="Search for valid users matching NAME" )
    parser.add_argument("-d", "--debug",
                        action='store_true',
                        help="Print Debugging Information" )
    conngroup = parser.add_argument_group( 'Connection Options' )
    conngroup.add_argument("-s", "--jiraserver",
                        help="Jira server to connect to. (cmdline or cfgfile)" )
    conngroup.add_argument("-u", "--jirauser",
                        help="Jira user name. (cmdline or cfgfile)" )
    conngroup.add_argument("-p", "--jirapass",
                        help="""Password for the jira account. (cmdline or cfgfile
                        or interactive-prompt).""" )
    conngroup.add_argument("-P", "--jiraproject",
                        help="Project to scan for. (cmdline or cfgfile)" )
    conngroup.add_argument('-f', "--cfgfile",
                        help="""Config file containing jira Connection information.
                        Ini-style format. Section "Connection" with one or more keys
                        matching the names of these Connection options 
                        (ie: jiraserver, jirauser, etc.)
                        Default: %(default)s
                        """)
    listgroup = parser.add_argument_group( 'List Options' )
    listgroup.add_argument("-l", "--list",
                        dest="list",
                        action='store_true',
                        help="List Open Tickets Assigned To Me.")
    listgroup.add_argument("-a", "--all",
                        dest="list_all",
                        action='store_true',
                        help="List All Open Tickets.")
    listgroup.add_argument("-c", "--cat",
                        dest="cat",
                        action='store_true',
                        help="Print the full contents of a ticket")
    modgroup = parser.add_argument_group( 'Modification Options' )
    modgroup.add_argument("-C","--comment",
                        action='store',
                        help="Add a comment to a ticket")
    modgroup.add_argument("-R","--resolve",
                        action='store_true',
                        help="Resolve a ticket (comment is required)")
    modgroup.add_argument("-T","--take",
                        dest="take",
                        action='store_true',
                        help="Assume ownership of the specified ticket")
    modgroup.add_argument("-G","--give",
                        action='store_true',
                        help="Give ownership to the user specified by the '-g' option")
    modgroup.add_argument("-g","--givetouser",
                        action='store',
                        help="User to give the ticket to (used with '-G' option)")
    parser.set_defaults(
        cfgfile = os.path.join( os.environ[ 'HOME' ], '.jiracmdline.cfg' )
        )
    args = parser.parse_args()
    # read defaults from config file
    cfgoptions = {}
    if os.path.isfile( args.cfgfile ):
        cfg = ConfigParser.SafeConfigParser()
        cfg.read( args.cfgfile )
        cfgoptions = dict( cfg.items( "Connection" ) )
    # use defaults for missing options (cmdline always overrides defaults)
    for k in [ 'jiraserver', 'jirauser', 'jiraproject' ]:
        if not getattr( args, k ):
            try:
                setattr( args, k, cfgoptions[ k ] )
            except ( KeyError ) as e:
                raise SystemExit( "Missing required option '{0}'".format( k ) )
    # get password
    if not args.jirapass:
        if 'jirapass' in cfgoptions:
            args.jirapass = cfgoptions[ 'jirapass' ]
        elif sys.stdin.isatty():
            args.jirapass = getpass.getpass()
        else:
            raise SystemExit( "Missing jira password" )
    # Check for mutually required params
    if args.give and not args.givetouser:
        raise SystemExit( "Givetouser is required with 'Give' option" )
    # Check for ticketlist on stdin
    # isatty() returns false if there's something in stdin
    if not sys.stdin.isatty():
        for elem in fileinput.input( '-' ):
            args.ticketlist.append( elem )
    # These options require tickets id's to be specified
    if args.give or args.take or args.resolve or args.comment:
        if len( args.ticketlist ) < 1:
            raise SystemExit( 'Ticket list required when using Modification Options' )
    return args


def jira_connect():
    opts = { 'server': args.jiraserver }
    return jira.client.JIRA( opts, basic_auth=( args.jirauser,args.jirapass ) )


def search_users( name ):
    return conn.search_users( name )


def is_valid_user( name ):
    for u in search_users( name ):
        if u.name == name:
            return True
    return False


def do_search():
#      for issue in jira.search_issues('assignee='+args.jira_user+' and project='+args.jira_project+' and status=open'):
    searchstr = ( 'assignee=currentUser() and '
                  'project={project} and '
                  'status in ("open","in progress")' 
                  ).format( project=args.jiraproject )
    if args.list_all:
        searchstr = ( 'project={project} and '
                      'status in ("open")'
                      ).format( project=args.jiraproject )
    return conn.search_issues( searchstr )
#          pprint.pprint( str( issue ) )
#          pprint.pprint( issue.raw )
#          print ""
#          raise SystemExit()


def print_issue( issue ):
    if args.cat:
        sep = '-'*50
        comments = [ sep ]
        for comment in issue.fields.comment.comments:
            c = conn.comment( issue.key, comment )
            comments.append( '\n'.join( map( str, [ c.updateAuthor, c.body ] ) ) )
            comments.append( sep )
        print( 'Ticket: {ticket}\n'
               'Summary: {summary}\n'
               'Description: {desc}\n'
               'Comments: \n{comments}\n'.format(
               ticket=issue.key,
               summary=issue.fields.summary,
               desc=issue.fields.description,
               comments='\n'.join( comments ) ) )
    else:
        print( '{0:8s}  {1}'.format( issue.key, issue.fields.summary ) )

def add_comment( issue ):
    conn.add_comment( issue, args.comment )
    print( 'Added comment: {0}'.format( args.comment ) )


def assign_issue( issue, new_user ):
    conn.assign_issue( issue, new_user )
    print( "Assigned issue to user '{0}'".format( new_user ) )


def resolve_issue( issue ):
    conn.transition_issue(issue, '5')
    print( "New state 'resolved'" )


def do_modify():
    for tid in args.ticketlist:
        issue = conn.issue( tid )
        print_issue( issue )
        if args.comment:
            add_comment( issue )
        if args.take:
            assign_issue( issue, args.jirauser )
        if args.give:
            if not is_valid_user( args.givetouser ):
                raise SystemExit( "Invalid user: '{0}'".format( args.givetouser ) )
            assign_issue( issue, args.givetouser )
        if args.resolve:
            resolve_issue( issue )
        print( '' )


if __name__ == '__main__':
    args = parse_cmdline()
    conn = jira_connect()

    if args.comment or args.resolve or args.take or args.give:
        do_modify()
    elif args.usersearch:
        matches = search_users( args.usersearch )
        pprint.pprint( matches )
    else:
        issues = []
        if len( args.ticketlist ) > 0:
            issues = [ conn.issue( tname ) for tname in args.ticketlist ]
        else:
            issues = [ conn.issue( i.key ) for i in do_search() ]
        for issue in issues:
            print_issue( issue )
