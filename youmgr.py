#!/usr/bin/python2

#import clewn.vim as vim; vim.pdb()
import wx
import urllib2
import os
import string
from sqlite3 import connect
from contextlib import closing
from lxml import etree
from multiprocessing import Process, Queue
from subprocess import PIPE, STDOUT, Popen
from threading import Thread
import time
import sys

class Parser:
    ''' xml parser to parse video query result '''
    def __init__(self):
        self.__reset()

    def get_data(self):
        ''' get videos list retrieved from parsed document '''
        return self.__videos

    def parse(self, data):
        ''' parse received data '''
        document = etree.XML(data)

        # look for entry elements, there may be more
        # then one
        for element in document:
            if 'entry' in element.tag:
                self.__parse_video_entry(element);

    def __parse_video_entry(self, entry):
        ''' parse video xml element '''
        author = None

        # get interesting data from entry
        for data in entry:
            if 'author' in data.tag:
                for field in data:
                    # get author name
                    if 'name' in field.tag:
                        author_name = field.text
            if 'group' in data.tag:
                video_title = None
                video_duration = None
                video_id = None
                video_description = None

                for field in data:
                    # get video title
                    if 'title' in field.tag:
                        video_title = field.text
                    # get video duration
                    elif 'duration' in field.tag:
                        video_duration = field.attrib['seconds']
                    # get video id
                    elif 'videoid' in field.tag:
                        video_id = field.text
                    # get video description
                    elif 'description' in field.tag:
                        video_description = field.text
                self.__videos.append((video_title,
                                      video_duration,
                                      video_id,
                                      video_description,
                                      author_name))

    def __reset(self):
        self.__videos = []

class ProxyDialog(wx.Dialog):
    ''' dialog window used to enter and edit proxy data '''
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Proxy settings', size=(300, 170))

        self.__home_path = wx.StandardPaths.Get().GetUserDataDir()
        selected_proxy = None

        # get proxy data
        with closing(connect(self.__home_path + '/ymdata.db')) as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM proxy WHERE selected = 1')
            selected_proxy = cursor.fetchone()

        # save proxy data for later use
        if selected_proxy:
            self.__proxy_url = selected_proxy[2]
            self.__proxy_port = selected_proxy[3]

        # set up the gui
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.__url_text_control = wx.TextCtrl(self) 
        self.__port_text_control = wx.TextCtrl(self)
        self.__ok_button = wx.Button(self, label='OK')
        self.Bind(wx.EVT_BUTTON, self.__on_ok, self.__ok_button)

        sizer.Add(wx.StaticText(self, label='Proxy address:'), 0, wx.ALL, 5)
        sizer.Add(self.__url_text_control, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(wx.StaticText(self, label='Proxy port:'), 0, wx.ALL, 5)
        sizer.Add(self.__port_text_control, 1, wx.ALL | wx.EXPAND, 5)
        sizer.Add(self.__ok_button, 0, wx.ALL, 5)

        # fill window with selected proxy data
        self.__url_text_control.SetValue(self.__proxy_url)
        self.__port_text_control.SetValue(self.__proxy_port)
        self.SetSizer(sizer)
        self.Layout()

    def get_proxy(self):
        ''' get proxy data as string '''
        return self.__proxy_url + ':' + self.__proxy_port

    def __on_ok(self, e):
        ''' ok button has been hit '''
        # get proxy data
        self.__proxy_url = self.__url_text_control.GetValue()
        self.__proxy_port = self.__port_text_control.GetValue()
        
        with closing(connect(self.__home_path + '/ymdata.db')) as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('UPDATE proxy SET addr="' + self.__proxy_url +\
                        '", port="' + self.__proxy_port + '" WHERE selected==1')
                connection.commit()
            except:
                dlg = wx.MessageDialog(self, 'Cannot save proxy settings!', 'Alert!')
                dlg.ShowModal()

        self.Close()

class VideoPanel(wx.Panel):
    ''' panel with video data displayed in the video view/library '''
    def __init__(self, parent, image, title, duration, description, author):
        wx.Panel.__init__(self, parent, style=wx.SIMPLE_BORDER)

        self.__home_path = wx.StandardPaths.Get().GetUserDataDir()

        # save the video data
        self.__image = image
        self.__title = title
        self.__duration = duration
        self.__description = description
        self.__author = author
        self.__link = None

        if self.__image:
            # create bitmap from image - only bitmap can be drawn
            self.__bitmap = wx.BitmapFromImage(self.__image)
            self.__image_width = image.GetSize()[0]
            self.SetSize(self.__image.GetSize())
        else:
            # no image
            self.__bitmap = None
            self.__image_width = 0
        self.Bind(wx.EVT_PAINT, self.__on_paint)

        self.SetCursor(wx.StockCursor(wx.CURSOR_HAND))

    def clone(self, parent):
        ''' clone this video panel and return the copy '''
        new_panel = VideoPanel(parent,
                               self.__image.Copy(),
                               self.__title,
                               self.__duration,
                               self.__description,
                               self.__author)
        new_panel.set_link(self.__link)
        return new_panel

    def set_link(self, link):
        ''' link setter '''
        self.__link = link

    def get_link(self):
        ''' link getter '''
        return self.__link

    def save_to_db(self):
        ''' save this video to database '''
        with closing(connect(self.__home_path + '/movies.db')) as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('INSERT INTO data VALUES (?,?,?,?,?,?,?,?) ',
                               self.__get_data_tuple())
                connection.commit()
            except:
                dlg = wx.MessageDialog(self,
                                       'Error occured while saving videos!')
                dlg.ShowModal()

    def remove_from_db(self):
        ''' remove this video from database '''
        with closing(connect(self.__home_path + '/movies.db')) as connection:
            cursor = connection.cursor()
            try:
                cursor.execute('DELETE FROM data WHERE author = ? AND\n'
                               'link = ? AND title = ? AND duration = ? AND\n'
                               'description = ? AND width = ? AND height = ?',
                               # we dont need image data for this
                               self.__get_data_tuple()[:-1])
                connection.commit()
            except:
                dlg = wx.MessageDialog(self,
                                       'Error occured while saving videos!')
                dlg.ShowModal()
       
    def __get_data_tuple(self):
        ''' get all the video data as tuple '''
        return (self.__author, self.__link, self.__title, self.__duration,
                self.__description, str(self.__image.GetWidth()),
                str(self.__image.GetHeight()), buffer(self.__image.GetData()))

    def __on_paint(self, e):
        ''' draw the panel '''
        dc = wx.PaintDC(self)
        if self.__title:
            font = dc.GetFont()
            font.SetWeight(wx.FONTWEIGHT_BOLD)
            dc.SetFont(font)
            dc.DrawText(self.__title, self.__image_width + 10, 10)
            font.SetWeight(wx.FONTWEIGHT_NORMAL)
            dc.SetFont(font)
        if self.__duration:
            dc.DrawText(self.__duration + ' ' + self.__author,
                        self.__image_width + 10,
                        30)
        if self.__description:
            dc.DrawText(self.__description, self.__image_width + 10, 50)
        if self.__bitmap:
            dc.DrawBitmap(self.__bitmap, 0, 0)
        e.Skip()

class VlcSettingsDialog(wx.Dialog):
    ''' dialog with settings for vlc player '''
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Vlc settings')

class MplSettingsDialog(wx.Dialog):
    ''' dialog with settings for mpv player '''
    def __init__(self, parent):
        wx.Dialog.__init__(self, parent, title='Mplayer settings')

class SavedVideosFrame(wx.Frame):
    ''' video library frame '''
    def __init__(self, parent):
        wx.Frame.__init__(self, parent, title='YouMgr video library')

        self.__home_path = wx.StandardPaths.Get().GetUserDataDir()
        self.__parent = parent
        self.__background_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.__results_panel = wx.ScrolledWindow(self)
        self.__results_panel.SetScrollbars(20,20,50,50)
        self.__results_sizer = wx.BoxSizer(wx.VERTICAL)
        self.__results_panel.SetSizer(self.__results_sizer)

        self.__background_sizer.Add(self.__results_panel, 1, wx.ALL | wx.EXPAND)

        self.SetSizer(self.__background_sizer)
        self.read_videos_from_db()

    def clone_and_add_panel(self, panel):
        ''' clone this panel and add to the videos list '''
        new_panel = panel.clone(self.__results_panel)
        new_panel.save_to_db()
        self.add_panel(new_panel)

    def add_panel(self, panel):
        ''' add panel to the videos list '''
        # attach event handlers for click and context menu
        panel.Bind(wx.EVT_LEFT_DOWN, self.__parent.on_play)
        panel.Bind(wx.EVT_RIGHT_DOWN, self.__on_context_menu)
        self.__results_sizer.Add(panel, 1, wx.TOP | wx.EXPAND, 1)
        self.Layout()

    def read_videos_from_db(self):
        ''' read all the videos from database and add them to library window '''
        videos_data = None
        with closing(connect(self.__home_path + '/movies.db')) as connection:
            cursor = connection.cursor()
            cursor.execute('SELECT * FROM data')
            videos_data = cursor.fetchall()

        # no videos exist in the databse
        if not videos_data:
            return

        # fill the panel with video panels
        for video_data in videos_data:
            panel = VideoPanel(self.__results_panel,
                               wx.ImageFromBuffer(video_data[5],
                                                  video_data[6],
                                                  video_data[7]),
                               unicode(video_data[2]),
                               video_data[3],
                               unicode(video_data[4]),
                               unicode(video_data[0]))
            panel.set_link(video_data[1])
            self.add_panel(panel)

    def __on_delete(self, e, panel):
        ''' delete panel from the videos list '''
        # do it gracefully, first hide
        panel.Hide()
        # detach from the list
        self.__results_sizer.Detach(panel)
        # remove child from the panel
        self.__results_panel.RemoveChild(panel)
        # remove from db
        panel.remove_from_db()
        self.Layout()

    def __on_context_menu(self, e):
        panel = e.GetEventObject()
        context_menu = wx.Menu()
        delete_menu_item = wx.MenuItem(context_menu, wx.ID_ANY, 'Delete')
        self.Bind(wx.EVT_MENU, lambda e: self.__on_delete(e, panel),
                  delete_menu_item)
        context_menu.AppendItem(delete_menu_item)
        panel.PopupMenu(context_menu, e.GetPosition())

class MainFrame(wx.Frame):
    ''' main application window '''
    def __init__(self):
        wx.Frame.__init__(self, None, title='YouMgr', size=(500,500))

        self.__retrieve_process = None
        self.__retrieve_queue = None
        self.__retrieve_timer = None

        self.__buttons = []
        self.__proxy_name = ':'
        self.__old_text = ''
        self.__index = 1
        self.__search_for_channel = False
        self.__gui = False
        self.__fulscreen = False
        self.__newsearch = False

        self.__played = []
        self.__player_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.__on_player_timer, self.__player_timer)
        self.__player_timer.Start(500)

        self.__background_sizer = wx.BoxSizer(wx.VERTICAL)
        self.__main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.__opt_sizer = wx.BoxSizer(wx.HORIZONTAL)

        #opt sizer
        self.__vlc_checkbox = wx.CheckBox(self, label='vlc')
        self.Bind(wx.EVT_CHECKBOX, self.__on_gui_change, self.__vlc_checkbox)

        self.__fulscreen_checkbox = wx.CheckBox(self, label='fulscreen')
        self.Bind(wx.EVT_CHECKBOX,
                  self.__on_fulscreen_change,
                  self.__fulscreen_checkbox)

        # video quality combo box
        self.__quality_combo_box =\
                wx.ComboBox(self, style=wx.CB_READONLY | wx.CB_DROPDOWN)
        self.__quality_combo_box.Append('Default', '0')
        self.__quality_combo_box.Append('MP4 270p-360p', '18')
        self.__quality_combo_box.Append('MP4 720p', '22')
        self.__quality_combo_box.Append('MP4 1080p', '37')
        self.__quality_combo_box.Append('WebM 360p', '43')
        self.__quality_combo_box.Append('WebM 480p', '44')
        self.__quality_combo_box.Append('WebM 720p', '45')
        self.__quality_combo_box.Append('WebM 1080p', '46')
        self.__quality_combo_box.SetSelection(0)

        self.__opt_sizer.Add(self.__vlc_checkbox, 0, wx.ALL, 5)
        self.__opt_sizer.Add(self.__fulscreen_checkbox, 0, wx.ALL, 5)
        self.__opt_sizer.Add(self.__quality_combo_box, 0, wx.ALL, 5)

        #main sizer
        self.__search_text = wx.TextCtrl(self)

        self.__search_button = wx.Button(self, label='New search')
        self.Bind(wx.EVT_BUTTON, self.__on_search, self.__search_button)

        self.__channel_checkbox = wx.CheckBox(self, label='channel')
        self.Bind(wx.EVT_CHECKBOX, self.__on_channel, self.__channel_checkbox)

        self.__results_panel = wx.ScrolledWindow(self)
        self.__results_panel.SetScrollbars(20,20,50,50)
        self.__results_sizer = wx.BoxSizer(wx.VERTICAL)
        self.__results_panel.SetSizer(self.__results_sizer)

        self.__main_sizer.Add(self.__search_text, 1, wx.ALL | wx.EXPAND, 5)
        self.__main_sizer.Add(self.__channel_checkbox, 0, wx.ALL, 5)
        self.__main_sizer.Add(self.__search_button, 0, wx.ALL, 5)

        #background sizer
        self.__background_sizer.Add(self.__main_sizer, 0, wx.ALL | wx.EXPAND)
        self.__background_sizer.Add(self.__opt_sizer, 0, wx.ALL | wx.EXPAND)
        self.__background_sizer.Add(self.__results_panel, 1,  wx.ALL | wx.EXPAND, 5)

        #menus
        self.__menu_bar = wx.MenuBar()

        file_menu = wx.Menu()
        proxy_menu = wx.MenuItem(file_menu, wx.ID_ANY, '&Proxy')
        exit_menu = wx.MenuItem(file_menu, wx.ID_EXIT, 'E&xit')

        players_menu = wx.Menu()
        vlc_menu = wx.MenuItem(players_menu, wx.ID_ANY, 'Vlc')
        mpl_menu = wx.MenuItem(players_menu, wx.ID_ANY, 'Mplayer')

        file_menu.AppendItem(proxy_menu)
        file_menu.AppendItem(exit_menu)
        self.Bind(wx.EVT_MENU, self.__on_proxy, proxy_menu)
        self.Bind(wx.EVT_MENU, self.__on_exit, exit_menu)

        players_menu.AppendItem(vlc_menu)
        players_menu.AppendItem(mpl_menu)
        self.Bind(wx.EVT_MENU, self.__on_vlc_settings, vlc_menu)
        self.Bind(wx.EVT_MENU, self.__on_mpl_settings, mpl_menu)

        self.__menu_bar.Append(file_menu, 'Options')
        self.__menu_bar.Append(players_menu, 'Players')

        self.__status_strip = wx.StatusBar(self)
        self.__status_strip.SetStatusText('Ready')

        #settings dialogs
        self.__proxy_dialog = ProxyDialog(self)
        self.__vlc_dialog = VlcSettingsDialog(self)
        self.__mpl_dialog = MplSettingsDialog(self)

        self.__search_text.Bind(wx.EVT_KEY_DOWN, self.__on_search_key_down)

        #library window
        self.__library_window = SavedVideosFrame(self)
        self.__library_window.Show(True)

        self.SetSizer(self.__background_sizer)
        self.SetMenuBar(self.__menu_bar)
        self.SetStatusBar(self.__status_strip)
        self.Layout()

    def on_play(self, e):
        ''' video has been clicked, play it '''
        link = e.GetEventObject().get_link()

        player = []

        self.__proxy_name = self.__proxy_dialog.get_proxy() 
        proxy = self.__proxy_name

        if proxy == ':':
            try:
                os.unsetenv['http_proxy']
                os.unsetenv['ftp_proxy']
            except:
                pass
        else:
            os.environ['http_proxy'] = self.__proxy_name
            os.environ['ftp_proxy'] = self.__proxy_name

        if self.__gui:
            player.append('vlc')

            if self.__fulscreen:
                player.append('-f')

            if proxy != ':':
                proxy = '--http-proxy=' + proxy + ' '
            else:
                proxy = ''

            #print(player + ' ' + proxy + link + ' &')
            #self.played.append(os.popen4(player + ' ' + proxy + link + ' &')[1])
            #print('nie blokuje')
        else:
            #player.append('mplayer')
            player.append('mpv')

            if self.__fulscreen:
                player.append('--fs')

            player.append('--cache 50000')
            player.append('--volume 50')
            player.append('--msglevel all=9')

            proxy = self.__proxy_dialog.get_proxy() 
            if proxy != ':':
                player.append('http_proxy://' + proxy + '/')
            else:
                player.append(':')

            quality_choice = self.__quality_combo_box.GetSelection()
            quality = self.__quality_combo_box.GetClientData(quality_choice)

            player.append(quality)
            player.append(link)

            queue = Queue()
            self.__played.append(queue)
            thread = Thread(target=play, args=(player, queue))
            thread.daemon = True
            thread.start()

    def __on_vlc_settings(self, e):
        ''' show vlc player settings window '''
        self.__vlc_dialog.ShowModal()

    def __on_mpl_settings(self, e):
        ''' show mplayer/mpv settings window '''
        self.__mpl_dialog.ShowModal()

    def __on_gui_change(self, e):
        ''' start player with gui or not '''
        self.__gui = not self.__gui

    def __on_fulscreen_change(self, e):
        ''' start player on fullscreen or not '''
        self.__fulscreen = not self.__fulscreen

    def __on_timer(self, e):
        '''
        check if there are results, if there are, process them. This is
        attached to a timer so, executed periodically when request has
        been sent
        '''
        while True:
            try:
                # get data from queue without blocking (exception if there
                # isn't any data available)
                data = self.__retrieve_queue.get_nowait()
            except:
                return

            # process data if there is something
            if len(data) is 1:
                # in this case it has to be a marking message
                if data[0] == 'End':
                    # end of data, everything has been received/processed
                    self.__status_strip.SetStatusText(\
                            'Search has been finished, ' +\
                            str(self.__index + 9) + ' results.')
                elif data[0] == 'Failed':
                    # error has occured
                    self.__status_strip.SetStatusText(\
                            'Search attempt has failed!')

                # clean up the queue and stop timer so this function
                # is not called until it is started from searching function
                self.__retrieve_timer.Stop()
                self.__retrieve_timer.Destroy()
                self.__retrieve_queue.close()

                self.__retrieve_process = None
                self.__retrieve_queue = None
                self.__retrieve_timer = None

            elif len(data) is 2:
                # this means that there is data, let's process it...
                if data[1]:
                    # there is image data
                    image = wx.ImageFromData(data[1][0], data[1][1], data[1][2])
                    self.__create_video_panel_for_video(data[0], image)
                else:
                    # no image data
                    self.__create_video_panel_for_video(data[0], None) 
        
    def __on_player_timer(self, e):
        '''
        this is timer function to process data from player (for instance
        progress data)
        '''
        # do that for all currently played videos (there can be more than one
        # this is a list of data queues
        for playing_video_queue in self.__played:
            data = None
            while True:
                try:
                    data = playing_video_queue.get_nowait()
                    #TODO: ehh I should fix this as well
                    if data == 'End':
                        # video has stopped, pop this queue from the list
                        self.__played.remove(playing_video_queue)
                        break
                except:
                    break
            if data:
                # remove unnecessary whitespaces and simply put this into the
                # status strip
                data.rstrip()
                self.__status_strip.SetStatusText(data)
            
    def __on_channel(self, e):
        ''' flip search for channel flag '''
        self.__search_for_channel = not self.__search_for_channel

    def __on_search_key_down(self, e):
        '''
        start searching if enter has been hit while in the searching bar
        '''
        key = e.GetKeyCode()
        if key == wx.WXK_RETURN:
            self.__search()
        else:
            e.Skip()

    def __on_search(self, e):
        '''
        executed when search button has been clicked, in this case start
        new search and discard all current results
        '''
        self.__newsearch = True
        self.__search()

    def __convert_seconds_to_hours_minutes_seconds(self, seconds):
        ''' convert seconds into HH:MM:SS format '''
        # just make sure...
        seconds = int(seconds)
        hours = seconds / 3600
        seconds = seconds - hours * 3600
        minutes = seconds / 60
        seconds = seconds - minutes * 60

        return str(hours).zfill(2) + ':' +\
               str(minutes).zfill(2) + ':' +\
               str(seconds).zfill(2)

    def __search(self):
        ''' search for videos as specified in the search text control '''
        # if there is retrieving process running, ignore this event
        # (don't search)
        if self.__retrieve_process:
            return

        # get search text
        text = self.__search_text.GetValue()
        self.__status_strip.SetStatusText('Searching for: ' + text + '...')

        # if it's different then in last search of we're searching for channel
        # or new search has been forced
        if text != self.__old_text or self.__search_for_channel or self.__newsearch:
            self.__results_sizer.Clear(True)
            self.__index = 1
            self.__search_for_channel = False
            self.__newsearch = False
        else:
            self.__index = self.__index + 10

        self.__old_text = text
        text = self.__prepare_query(text)

        # prepare query strings
        if self.__channel_checkbox.GetValue():
            query = 'http://gdata.youtube.com/feeds/api/users/' + text +\
                    '/uploads?start-index=' + str(self.__index) +\
                    '&max-results=10&v=2&prettyprint=true'
        else:
            query = 'http://gdata.youtube.com/feeds/api/videos?q=' + text +\
                    '&start-index=' + str(self.__index) +\
                    '&max-results=10&v=2&prettyprint=true'
                
        self.__proxy_name = self.__proxy_dialog.get_proxy()

        # set up new retrieval timer
        self.__retrieve_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.__on_timer, self.__retrieve_timer)

        # set up new queue for results processing and start new retrieval
        # process and resume retrieval timer
        self.__retrieve_queue = Queue()
        self.__retrieve_process =\
                Process(target=retrieve, args=(self.__proxy_name,
                                               self.__retrieve_queue, query))
        self.__retrieve_process.start()
        self.__retrieve_timer.Start(50)
    
    def __create_video_panel_for_video(self, data, image):
        ''' parse video data and create video panel '''
        title = data[0]
        time = self.__convert_seconds_to_hours_minutes_seconds(data[1])
        link = 'http://www.youtube.com/watch?v=' + data[2]

        # build the panel and set up all the connections
        panel = VideoPanel(self.__results_panel, image, title, time, data[3], data[4])
        panel.set_link(link)
        panel.Bind(wx.EVT_LEFT_DOWN, self.on_play)
        panel.Bind(wx.EVT_RIGHT_DOWN, self.__on_context_menu)

        self.__results_sizer.Add(panel, 1, wx.TOP | wx.EXPAND, 1)
        self.Layout()

    def __on_context_menu(self, e):
        ''' show video context menu '''
        panel = e.GetEventObject()
        menu = wx.Menu()

        save = wx.MenuItem(menu, wx.ID_ANY, 'Save')
        self.Bind(wx.EVT_MENU, lambda e: self.__on_save(e, panel), save)

        download = wx.MenuItem(menu, wx.ID_ANY, 'Download')
        self.Bind(wx.EVT_MENU, lambda e: self.__on_download(e, panel), download)

        menu.AppendItem(save)
        menu.AppendItem(download)
        panel.PopupMenu(menu, e.GetPosition())

    def __on_save(self, e, panel):
        ''' save the video to the library (database)'''
        self.__library_window.clone_and_add_panel(panel)

    def __on_download(self, e, panel):
        ''' download this video '''
        # TODO: fix this...
        proxy = self.__proxy_dialog.get_proxy() 
        if proxy != ':':
            os.environ['http_proxy'] = self.__proxy_name
            os.environ['ftp_proxy'] = self.__proxy_name
        os.system('youtube-dl ' + panel.link + ' &')

    def __prepare_query(self, text):
        ''' prepare query from text control to be inserted into url '''
        was_white = True
        new_text = ''
        for character in text:
            # space
            if character == ' ':
                if was_white:
                    # if there was white before, process next character
                    # we already have + inserted
                    continue
                else:
                    # insert + instead of space
                    new_text = new_text + '+'
                    was_white = True
            else:
                # if not white, just copy it
                new_text = new_text + character 
                was_white = False

        # if there are any + on the edges, get rid of them, they are not
        # necessary
        return new_text.strip('+')

    def __on_proxy(self, e):
        ''' show proxy settings dialog '''
        self.__proxy_dialog.ShowModal()
        self.__proxy_name = self.__proxy_dialog.get_proxy()

    def __on_exit(self, e):
        ''' exit event has been received '''
        self.__quit()

    def __quit(self):
        ''' exit the program '''
        exit()

def play(command, queue):
    '''
    open new process, with player and connect it to get data from the player
    '''
    if command[-2] == '0':
        process = Popen(['youtube-dl','--get-url', command[-1]], stdout=PIPE,\
                         stderr=STDOUT, bufsize=1)
    else:
        process = Popen(['youtube-dl','--format', command[-2], '--get-url',\
                         command[-1]], stdout=PIPE, stderr=STDOUT, bufsize=1)

    url = ''
    queue.put('Retrieving video URL...')

    while True:
        data = process.stdout.read(512)
        if data == '':
            break
        else:
            url = url + data

    url = url.rstrip()

    if len(url.split('\n')) == 1:
        queue.put('Video URL has been successfully obtained!')
        player = []

        for a in command[:1]:
            player.append(a)

        if command[-3] != ':':
            player.append(command[-3] + url)
        else:
            player.append(url)

        process = Popen(player, stdout=PIPE, stdin=PIPE, stderr=STDOUT,\
                        bufsize=0)
        readLine = True
        last = ''

        while True:
            if process.poll() is not None:
                break
            lines =\
                str(process.stdout.read(128)).replace('\r', '\n').split('\n')
            lines[0] = last + lines[0]
            last = lines.pop()
            for l in lines:
                queue.put(l)

        queue.put('End')
    else:
        queue.put('Could not retrieve an URL for the video!')

def retrieve(proxy, queue, url):
    ''' get data for given url, parse it and get image '''
    parser = Parser()

    try:
        parser.parse(fetch_url(proxy, url).read())
    except: 
        queue.put(['Fail'])
        return

    for data in parser.get_data():
        image = retrieve_image_data(proxy, data)
        queue.put([data, image])

    queue.put(['End'])

def retrieve_image_data(proxy, data):
    '''
    get image data and create wx image from it so it can be easily processed
    '''
    thumb = 'http://i.ytimg.com/vi/' + data[2] + '/default.jpg'

    try:
        image = wx.ImageFromStream(fetch_url(proxy, thumb), type=wx.BITMAP_TYPE_JPEG)
        return (image.GetWidth(), image.GetHeight(), image.GetData())
    except:
        return None

def fetch_url(proxy, url):
    ''' get url data using proxy when necessary '''
    if proxy != ':':
        return urllib2.build_opener(urllib2.ProxyHandler({'http': proxy })).open(url)
    else:
        return urllib2.urlopen(url)

app = wx.App(False)
app.SetAppName('youmgr')
wnd = MainFrame()
wnd.Show(True)
wnd.Maximize()
app.MainLoop()
